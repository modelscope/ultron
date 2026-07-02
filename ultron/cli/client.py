# Copyright (c) ModelScope Contributors. All rights reserved.
"""HTTP client for ultron's agent-repository API.

Endpoints:

* ``GET  /openapi/v1/users/me``                            → login
* ``GET  /openapi/v1/agents/{path}/{name}``                → repo metadata
* ``POST /openapi/v1/agents``                              → create/update agent
* ``GET  /openapi/v1/agents/{path}/{name}/repo/files``     → list files
* ``GET  /agents/{path}/{name}/resolve/{rev}/{file}``      → file download
* ``POST /api/v1/agents/repo/files/upload``                → two-step OSS upload (step1)
* ``POST /openapi/v1/agents/{path}/{name}/commit/{rev}``   → commit files
"""
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import unquote

import requests
from modelscope_hub._openapi import OpenAPIClient
from modelscope_hub.config import HubConfig
from modelscope_hub.errors import HubError, NotExistError

logger = logging.getLogger("ultron.cli")


@dataclass
class RemoteFileInfo:
    """Metadata for a single file in the remote repository."""
    path: str
    sha256: str
    committed_date: int  # unix timestamp


class ApiError(Exception):
    """Raised for non-2xx API responses; carries the HTTP status code."""

    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"HTTP {status}: {detail}")


def _wrap(exc: HubError) -> ApiError:
    """Convert a modelscope_hub error into an ApiError."""
    status = getattr(exc, "status_code", None) or 0
    return ApiError(status, str(exc.message))


class UltronClient:
    def __init__(self, server: str, token: Optional[str] = None, timeout: int = 60):
        self.server = server.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._config = HubConfig(endpoint=self.server, token=token)
        self._openapi = OpenAPIClient(config=self._config, timeout=float(timeout))

    # ---- auth ----

    def login(self, token: str) -> str:
        """Validate token via GET /openapi/v1/users/me, return username."""
        try:
            self._config.token = token
            self.token = token
            data = self._openapi.get_current_user()
        except HubError as exc:
            raise _wrap(exc) from exc
        return data.get("username") or data.get("Username") or ""

    # ---- repository ----

    def repo_info(self, path: str, name: str) -> Optional[dict]:
        """Repo metadata or None if the repo does not exist (404)."""
        try:
            return self._openapi._request("GET", f"/agents/{path}/{name}")
        except NotExistError:
            return None
        except HubError as exc:
            raise _wrap(exc) from exc

    def check_repo(self, path: str, name: str) -> bool:
        """True if the repo exists, False on 404."""
        return self.repo_info(path, name) is not None

    def list_agents(self, owner: Optional[str] = None, page_number: int = 1, page_size: int = 10) -> dict:
        """List agent repositories (GET /agents).

        Returns a dict with 'items' (list of agent metadata dicts) and
        'total_count' (int).
        """
        params = {"page_number": page_number, "page_size": page_size}
        if owner:
            params["owner"] = owner
        try:
            data = self._openapi._request(
                "GET", "/agents", params=params, require_token=False)
        except HubError as exc:
            raise _wrap(exc) from exc
        if isinstance(data, list):
            return {"items": data, "total_count": len(data)}
        if isinstance(data, dict):
            items = data.get("Data") or []
            total = data.get("Total") or data.get("TotalCount") or len(items)
            return {"items": items, "total_count": total}
        return {"items": [], "total_count": 0}

    def create_repo(
        self, path: str, name: str, framework: str,
        visibility: str = "public",
        system_prompt_files: Optional[str] = None,
    ) -> dict:
        """Create or update an agent (POST /agents).

        When *system_prompt_files* is provided the server uses the uploaded
        file as the agent content ("新增和更新重叠使用本方法").
        """
        body: dict = {
            "path": path,
            "name": name,
            "framework": framework,
            "visibility": visibility,
        }
        if system_prompt_files:
            body["system_prompt_files"] = system_prompt_files
        try:
            return self._openapi._request("POST", "/agents", json_body=body)
        except HubError as exc:
            raise _wrap(exc) from exc

    def list_repo_files(self, path: str, name: str, revision: str = 'master') -> List[str]:
        """All file paths in the repo, recursing into sub-directories."""
        entries = self._fetch_tree_entries(path, name, revision)
        return [e["path"] for e in entries if e["type"] == "blob" and e["path"]]

    def list_repo_files_detail(self, path: str, name: str, revision: str = 'master') -> List[RemoteFileInfo]:
        """All blob files with sha256 and committed_date.

        Returns a list of ``RemoteFileInfo`` for each blob entry in the repo.
        Raises ``ApiError(404, ...)`` if the repo does not exist.
        """
        entries = self._fetch_tree_entries(path, name, revision)
        results: List[RemoteFileInfo] = []
        for item in entries:
            if item["type"] != "blob" or not item["path"]:
                continue
            results.append(RemoteFileInfo(
                path=item["path"],
                sha256=item.get("sha256") or "",
                committed_date=int(item.get("committed_date") or 0),
            ))
        return results

    def _fetch_tree_entries(self, path: str, name: str, revision: str) -> List[dict]:
        """Fetch and normalize the repo file tree from the API (with pagination)."""
        page = 1
        page_size = 100
        max_pages = 50  # safety cap: 5000 files max
        all_entries: List[dict] = []

        while True:
            try:
                data = self._openapi._request(
                    "GET", f"/agents/{path}/{name}/repo/files",
                    params={
                        "recursive": "true",
                        "page_size": str(page_size),
                        "page": str(page),
                        "revision": revision,
                    },
                )
            except HubError as exc:
                raise _wrap(exc) from exc

            raw = []
            if isinstance(data, dict):
                raw = data.get("Trees") or data.get("trees") or []
            elif isinstance(data, list):
                raw = data

            for item in raw:
                if not isinstance(item, dict):
                    continue
                all_entries.append({
                    "path": item.get("Path") or item.get("path") or "",
                    "type": item.get("Type") or item.get("type") or "",
                    "sha256": item.get("Sha256") or item.get("sha256") or "",
                    "committed_date": item.get("Committed_date") or item.get("committed_date") or 0,
                })

            if len(raw) < page_size:
                break
            page += 1
            if page > max_pages:
                logger.warning(
                    "Pagination limit reached (%d pages) for %s/%s; results may be incomplete.",
                    max_pages, path, name,
                )
                break

        return all_entries

    def download_repo_file(self, path: str, name: str, file_path: str,
                           revision: str = "master", *, binary: bool = False):
        """Download one repo file (GET /agents/{path}/{name}/resolve/{revision}/{file_path}).

        This endpoint does NOT use the /openapi/v1/ prefix.
        Returns bytes when *binary=True*, otherwise str.
        """
        url = f"{self.server}/agents/{path}/{name}/resolve/{revision}/{file_path}"
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            resp = requests.get(url, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            detail = exc.response.text if exc.response is not None else str(exc)
            raise ApiError(status, detail) from exc
        except requests.RequestException as exc:
            raise ApiError(0, str(exc)) from exc
        return resp.content if binary else resp.text

    # ---- upload (two-step OSS) ----

    def _request_upload_urls(self, filenames: List[str]) -> dict:
        """Step 1: POST /api/v1/agents/repo/files/upload → {Gid, Urls}.

        Uses /api/v1/ prefix (not /openapi/v1/). Response envelope uses
        capitalised keys: {"Code": 200, "Data": {...}, "Success": true}.
        """
        url = f"{self.server}/api/v1/agents/repo/files/upload"
        headers = {"Authorization": f"Bearer {self.token}",
                   "Content-Type": "application/json"}
        try:
            resp = requests.post(url, json={"FileNames": filenames},
                                headers=headers, timeout=self.timeout)
            resp.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            detail = exc.response.text if exc.response is not None else str(exc)
            raise ApiError(status, detail) from exc
        except requests.RequestException as exc:
            raise ApiError(0, str(exc)) from exc
        body = resp.json()
        if not body.get("Success"):
            raise ApiError(body.get("Code", 0), body.get("Message", "upload credential failed"))
        return body["Data"]

    @staticmethod
    def _normalize_oss_url(url: str) -> str:
        """Decode %2F in the URL path so OSS signature verification passes.

        The server may return signed URLs with path separators encoded as %2F.
        OSS computes the signature on the *decoded* resource path, so we must
        send the request with real '/' in the path.  We only decode the path
        portion (before '?') to avoid corrupting query-string parameters.
        """
        parts = url.split("?", 1)
        path_part = parts[0]
        if "%2F" not in path_part and "%2f" not in path_part:
            return url
        decoded_path = unquote(path_part)
        if len(parts) == 2:
            return decoded_path + "?" + parts[1]
        return decoded_path

    def _upload_to_oss(self, signed_url: str, data: bytes) -> None:
        """Step 2: PUT raw bytes to signed OSS URL.

        The server signs the URL with these headers in the StringToSign:
        - Content-Type: application/octet-stream
        - x-oss-meta-author: aliy  (included in CanonicalizedOSSHeaders)
        Both MUST be present for the signature to match.

        COUPLING: These headers are dictated by the server-side signing config.
        If the server changes its signing parameters, these must be updated
        in lockstep.
        """
        url = self._normalize_oss_url(signed_url)
        try:
            resp = requests.put(url, data=data,
                                headers={
                                    "Content-Type": "application/octet-stream",
                                    "x-oss-meta-author": "aliy",
                                },
                                timeout=max(self.timeout, 300))
            resp.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            detail = exc.response.text if exc.response is not None else str(exc)
            raise ApiError(status, detail) from exc
        except requests.RequestException as exc:
            raise ApiError(0, str(exc)) from exc

    def upload_file(self, resources: Dict[str, bytes]) -> str:
        """Two-step upload: get signed URLs → PUT to OSS → return Gid.

        The returned Gid (UUID) is used as ``system_prompt_files`` in
        :meth:`create_repo`.

        Returns empty string if *resources* is empty (nothing to upload).
        """
        if not resources:
            logger.warning("upload_file called with empty resources; skipping.")
            return ""
        filenames = list(resources.keys())
        data = self._request_upload_urls(filenames)
        gid = data["Gid"]
        url_map = {item["Filename"]: item["Url"] for item in data["Urls"]}
        for fname, content in resources.items():
            signed_url = url_map.get(fname)
            if not signed_url:
                raise ApiError(
                    0,
                    f"Server did not return a signed URL for '{fname}'. "
                    f"Available: {list(url_map.keys())}",
                )
            self._upload_to_oss(signed_url, content)
        return gid

    # ---- commit (incremental) ----

    def commit_files(self, path: str, name: str, actions: List[dict],
                     revision: str = "master", commit_message: str = "sync") -> dict:
        """Commit file changes via POST /openapi/v1/agents/{path}/{name}/commit/{revision}.

        *actions* example::

            [{"action": "create", "file_path": "a.md",
              "content": "hello", "encoding": "text"}]
        """
        body = {"commit_message": commit_message, "actions": actions}
        try:
            return self._openapi._request(
                "POST", f"/agents/{path}/{name}/commit/{revision}", json_body=body)
        except HubError as exc:
            raise _wrap(exc) from exc
