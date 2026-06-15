# Copyright (c) ModelScope Contributors. All rights reserved.
"""Minimal HTTP client over ultron's auth + agent-repository API.

Uses the standard library only (``urllib``) so the CLI has no extra
dependencies. It speaks the same endpoints the dashboard and the
``/api/v1/agents/*`` repository contract expose:

* ``POST /auth/login``                                  -> token
* ``GET  /api/v1/agents/{path}/{name}``                 -> repo exists?
* ``POST /api/v1/agents``                               -> create repo
* ``POST /api/v1/files/upload``                         -> upload a zip snapshot
* ``GET  /api/v1/agents/{path}/{name}/repo/files``      -> list repo files
* ``GET  /api/v1/agents/{path}/{name}/repo``            -> file download link

Uploads send the whole sub-agent directory as a single ``.zip`` so the server
receives a complete snapshot and can derive updates *and* deletes; piecemeal
per-file commits can't express "this file was removed". (The older per-file
``commit`` path is kept on this client but is no longer used by ``ultron
upload``.)
"""
import json
import os
import urllib.error
import urllib.request
from typing import List, Optional


class ApiError(Exception):
    """Raised for non-2xx API responses; carries the HTTP status code."""

    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"HTTP {status}: {detail}")


class UltronClient:
    def __init__(self, server: str, token: Optional[str] = None, timeout: int = 60):
        self.server = server.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        url = f"{self.server}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = _extract_detail(e)
            raise ApiError(e.code, detail)
        except urllib.error.URLError as e:
            raise ApiError(0, f"Cannot reach {self.server}: {e.reason}")
        return json.loads(raw) if raw else {}

    def _post_multipart(
        self, path: str, fields: dict, file_field: str, filename: str, file_bytes: bytes
    ) -> dict:
        """POST a ``multipart/form-data`` body (text fields + one file part)."""
        url = f"{self.server}{path}"
        boundary = "----ultron" + os.urandom(16).hex()
        body = _encode_multipart(boundary, fields, file_field, filename, file_bytes)
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raise ApiError(e.code, _extract_detail(e))
        except urllib.error.URLError as e:
            raise ApiError(0, f"Cannot reach {self.server}: {e.reason}")
        return json.loads(raw) if raw else {}

    def _get_bytes(self, url: str) -> bytes:
        """GET a (possibly relative) URL and return the raw response body."""
        if not url.startswith(("http://", "https://")):
            url = f"{self.server}/{url.lstrip('/')}"
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            raise ApiError(e.code, _extract_detail(e))
        except urllib.error.URLError as e:
            raise ApiError(0, f"Cannot reach {url}: {e.reason}")

    # ---- auth ----

    def login(self, username: str, password: str) -> str:
        resp = self._request(
            "POST", "/auth/login", {"username": username, "password": password}
        )
        return resp["data"]["token"]

    # ---- repository ----

    def repo_info(self, path: str, name: str) -> Optional[dict]:
        """Repo metadata ``{Path, Name, Framework, Revision, ...}`` or None on 404."""
        try:
            resp = self._request("GET", f"/api/v1/agents/{path}/{name}")
            return resp.get("data", {})
        except ApiError as e:
            if e.status == 404:
                return None
            raise

    def check_repo(self, path: str, name: str) -> bool:
        """True if the repo exists, False on 404."""
        return self.repo_info(path, name) is not None

    def create_repo(self, path: str, name: str, framework: str) -> dict:
        return self._request(
            "POST",
            "/api/v1/agents",
            {"Path": path, "Name": name, "Framework": framework},
        )

    def commit(
        self, path: str, name: str, actions: List[dict], message: str
    ) -> dict:
        """Per-file commit (legacy). ``ultron upload`` now uses ``upload_zip``."""
        return self._request(
            "POST",
            f"/api/v1/repos/agents/{path}/{name}/commit/master",
            {"commit_message": message, "actions": actions},
        )

    def upload_zip(
        self,
        path: str,
        name: str,
        framework: str,
        zip_bytes: bytes,
        message: str,
    ) -> dict:
        """Upload a whole-directory ``.zip`` snapshot of a repo.

        The zip is the complete file set for ``path/name``; the server replaces
        the repo contents from it (so removed files become deletes). Repo
        coordinates ride alongside the file as ``multipart/form-data`` fields.
        """
        fields = {
            "Path": path,
            "Name": name,
            "Framework": framework,
            "commit_message": message,
        }
        return self._post_multipart(
            "/api/v1/files/upload", fields, "file", f"{name}.zip", zip_bytes
        )

    def list_repo_files(self, path: str, name: str) -> List[str]:
        """All file paths in the repo (follows pagination)."""
        files: List[str] = []
        page = 1
        while True:
            resp = self._request(
                "GET",
                f"/api/v1/agents/{path}/{name}/repo/files"
                f"?Recursive=true&PageNumber={page}&PageSize=100",
            )
            data = resp.get("data", {})
            batch = data.get("Files", [])
            files.extend(f["Path"] for f in batch)
            if page * data.get("PageSize", 100) >= data.get("Total", len(files)):
                break
            page += 1
        return files

    def get_file_download_url(self, path: str, name: str, file_path: str) -> str:
        """Resolve a file's download link via the repo's download-link endpoint."""
        from urllib.parse import quote

        resp = self._request(
            "GET",
            f"/api/v1/agents/{path}/{name}/repo?FilePath={quote(file_path)}",
        )
        data = resp.get("data", {})
        # Accept the common spellings a hub backend might use for the link field.
        for key in ("Url", "DownloadUrl", "Link", "url", "download_url"):
            if data.get(key):
                return data[key]
        raise ApiError(0, f"no download URL in response for '{file_path}'")

    def download_repo_file(self, path: str, name: str, file_path: str) -> str:
        """Download one repo file via its download link, decoded to UTF-8 text."""
        url = self.get_file_download_url(path, name, file_path)
        return self._get_bytes(url).decode("utf-8")


def _encode_multipart(
    boundary: str, fields: dict, file_field: str, filename: str, file_bytes: bytes
) -> bytes:
    """Build a ``multipart/form-data`` body from text fields and one file part."""
    crlf = b"\r\n"
    dash = b"--" + boundary.encode("ascii")
    parts: List[bytes] = []
    for key, value in fields.items():
        parts.append(dash)
        parts.append(
            f'Content-Disposition: form-data; name="{key}"'.encode("utf-8")
        )
        parts.append(b"")
        parts.append(str(value).encode("utf-8"))
    parts.append(dash)
    parts.append(
        f'Content-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"'.encode("utf-8")
    )
    parts.append(b"Content-Type: application/zip")
    parts.append(b"")
    # The file bytes are appended raw (not joined with the text parts).
    head = crlf.join(parts) + crlf
    tail = crlf + dash + b"--" + crlf
    return head + file_bytes + tail


def _extract_detail(e: "urllib.error.HTTPError") -> str:
    try:
        payload = json.loads(e.read().decode("utf-8"))
        return payload.get("detail") or payload.get("message") or str(payload)
    except Exception:
        return e.reason or "request failed"
