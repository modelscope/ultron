# Copyright (c) ModelScope Contributors. All rights reserved.
"""HTTP client for ultron's agent-repository API.

Endpoints:

* ``GET  /openapi/v1/users/me``                            → login
* ``GET  /openapi/v1/agents/{path}/{name}``                → repo metadata
* ``POST /openapi/v1/agents``                              → create empty agent
* ``GET  /api/v1/agents/{path}/{name}/repo/files``         → list files
* ``GET  /agents/{path}/{name}/resolve/{rev}/{file}``      → file download
* ``POST /api/v1/repos/agents/{id}/commit/{rev}``          → commit files (normal/lfs)
* ``POST /api/v1/repos/agents/{id}/info/lfs/objects/batch`` → LFS batch verify
* ``DELETE /api/v1/agents/{path}/{name}/repo/file``        → delete file
"""
import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import unquote

import requests
from modelscope_hub._openapi import OpenAPIClient
from modelscope_hub.config import HubConfig
from modelscope_hub.errors import HubError, NotExistError

logger = logging.getLogger("ultron.cli")

# LFS file extensions that must use LFS upload pathway.
_LFS_EXTENSIONS: frozenset = frozenset({
    ".7z", ".aac", ".arrow", ".audio", ".bin", ".bmp", ".bz2",
    ".ckpt", ".flac", ".ftz", ".gif", ".gz", ".h5",
    ".jack", ".jpeg", ".jpg", ".joblib", ".jsonl",
    ".lz4", ".mlmodel", ".model", ".mp3", ".mp4", ".msgpack",
    ".npy", ".npz", ".ogg", ".onnx", ".ot",
    ".parquet", ".pb", ".pcm", ".pickle", ".pkl", ".png",
    ".pt", ".pth", ".rar", ".raw",
    ".safetensors", ".sam", ".tar", ".tflite", ".tgz", ".tiff",
    ".wasm", ".wav", ".webm", ".webp", ".xz", ".zip", ".zst",
})

# Files larger than this threshold (bytes) use LFS upload.
_LFS_SIZE_THRESHOLD: int = 1 * 1024 * 1024  # 1 MB


def is_lfs_file(file_path: str, size: int) -> bool:
    """Determine whether a file should use LFS upload.

    A file is considered LFS if:
    1. Its extension is in the known LFS extension set, OR
    2. Its size exceeds the LFS threshold (1 MB).
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext in _LFS_EXTENSIONS:
        return True
    if size > _LFS_SIZE_THRESHOLD:
        return True
    return False


@dataclass
class RemoteFileInfo:
    """Metadata for a single file in the remote repository."""
    path: str
    sha256: str
    committed_date: int  # unix timestamp
    is_lfs: bool = False


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
        return data.get("username", data.get("Username", ""))

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
        # Normalize response: server may return {Data: [...], Total: N}
        # or {items: [...], total_count: N}.
        if isinstance(data, dict):
            items = None
            for key in ("Data", "items", "data"):
                if key in data:
                    items = data[key]
                    break
            if items is None:
                items = []
            total = data.get("Total")
            if total is None:
                total = data.get("total_count")
            if total is None:
                total = data.get("TotalCount")
            if total is None:
                total = len(items)
            return {"items": items, "total_count": total}
        # If response is a list directly
        if isinstance(data, list):
            return {"items": data, "total_count": len(data)}
        return {"items": [], "total_count": 0}

    def create_repo(self, path: str, name: str, framework: str | None = None) -> dict:
        """Create an empty agent (POST /agents).

        The server creates a bare repository.  Files are added separately via
        :meth:`commit_files`.

        Args:
            framework: Optional product/framework identifier stored with the
                       repo (e.g. "qoder", "nanobot").  Defaults to server-side
                       default when omitted.
        """
        body: dict = {"path": path, "name": name}
        if framework:
            body["framework"] = framework
        try:
            return self._openapi._request("POST", "/agents", json_body=body)
        except HubError as exc:
            raise _wrap(exc) from exc

    def list_repo_files(self, path: str, name: str, revision: str = 'master') -> List[str]:
        """All file paths in the repo, recursing into sub-directories."""
        entries = self._fetch_tree_entries(path, name, revision)
        return [e["path"] for e in entries if e["type"] == "blob" and e["path"]]

    def list_repo_files_detail(self, path: str, name: str, revision: str = 'master') -> List[RemoteFileInfo]:
        """All blob files with sha256, committed_date, and is_lfs flag."""
        entries = self._fetch_tree_entries(path, name, revision)
        results: List[RemoteFileInfo] = []
        for item in entries:
            if item["type"] != "blob" or not item["path"]:
                continue
            results.append(RemoteFileInfo(
                path=item["path"],
                sha256=item.get("sha256") or "",
                committed_date=int(item.get("committed_date") or 0),
                is_lfs=bool(item.get("is_lfs", False)),
            ))
        return results

    def _fetch_tree_entries(self, path: str, name: str, revision: str) -> List[dict]:
        """Fetch and normalize the repo file tree from the API (with pagination)."""
        page = 1
        page_size = 100
        max_pages = 50  # safety cap: 5000 files max
        all_entries: List[dict] = []

        list_url = f"{self.server}/api/v1/agents/{path}/{name}/repo/files"
        while True:
            try:
                data = self._openapi._request(
                    "GET", url=list_url,
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
                raw = data.get("trees") or data.get("Trees") or []
            elif isinstance(data, list):
                raw = data

            for item in raw:
                if not isinstance(item, dict):
                    continue
                all_entries.append({
                    "path": item.get("path") or item.get("Path") or "",
                    "type": item.get("type") or item.get("Type") or "",
                    "sha256": item.get("sha256") or item.get("Sha256") or "",
                    "committed_date": item.get("committed_date") or item.get("Committed_date") or 0,
                    "is_lfs": bool(item.get("IsLfs") or item.get("is_lfs") or False),
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

    # ---- commit (normal + LFS) ----

    def commit_files(self, path: str, name: str, actions: List[dict],
                     revision: str = "master", commit_message: str = "sync") -> dict:
        """Commit file changes via POST /api/v1/repos/agents/{path}/{name}/commit/{revision}.

        Each action dict should contain:
          - action: "create" | "update" | "delete"
          - path: file path in repo
          - type: "normal" | "lfs"  (for create/update)
          - size: file size in bytes (for create/update)
          - sha256: sha256 hash (required for lfs; empty string for normal)
          - content: base64-encoded content (for normal) or empty (for lfs)
          - encoding: "base64" (for normal) or "" (for lfs)
        """
        commit_url = f"{self.server}/api/v1/repos/agents/{path}/{name}/commit/{revision}"
        body = {"commit_message": commit_message, "actions": actions}
        try:
            return self._openapi._request("POST", url=commit_url, json_body=body)
        except HubError as exc:
            raise _wrap(exc) from exc

    def lfs_batch(self, path: str, name: str, oid: str, size: int) -> Optional[str]:
        """LFS batch verify and return upload URL (or None if already exists).

        POST /api/v1/repos/agents/{path}/{name}/info/lfs/objects/batch
        Returns the upload href if the server needs the blob, None otherwise.
        """
        batch_url = (
            f"{self.server}/api/v1/repos/agents/{path}/{name}"
            f"/info/lfs/objects/batch"
        )
        body = {
            "operation": "upload",
            "objects": [{"oid": oid, "size": size}],
        }
        try:
            data = self._openapi._request("POST", url=batch_url, json_body=body)
        except HubError as exc:
            raise _wrap(exc) from exc
        objects = []
        if isinstance(data, dict):
            objects = data.get("objects") or []
        if not objects:
            return None
        upload_info = objects[0].get("actions", {}).get("upload", {})
        return upload_info.get("href") or None

    def lfs_upload_blob(self, upload_url: str, data: bytes) -> None:
        """PUT binary data to the LFS upload URL."""
        try:
            resp = requests.put(
                upload_url, data=data,
                headers={"Content-Type": "application/octet-stream"},
                timeout=max(self.timeout, 300),
            )
            resp.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            detail = exc.response.text if exc.response is not None else str(exc)
            raise ApiError(status, detail) from exc
        except requests.RequestException as exc:
            raise ApiError(0, str(exc)) from exc

    def upload_lfs_file(self, path: str, name: str, file_path: str,
                        content: bytes, action: str = "create",
                        revision: str = "master",
                        commit_message: str = "sync") -> dict:
        """Full LFS upload flow: batch verify -> PUT blob -> commit reference."""
        oid = hashlib.sha256(content).hexdigest()
        size = len(content)

        # Step 1: batch verify
        upload_url = self.lfs_batch(path, name, oid, size)
        # Step 2: PUT blob if needed
        if upload_url:
            self.lfs_upload_blob(upload_url, content)

        # Step 3: commit LFS reference
        actions = [{
            "action": action,
            "path": file_path,
            "type": "lfs",
            "size": size,
            "sha256": oid,
            "content": "",
            "encoding": "",
        }]
        return self.commit_files(path, name, actions, revision=revision,
                                 commit_message=commit_message)

    def delete_file(self, path: str, name: str, file_path: str,
                    revision: str = "master",
                    commit_message: Optional[str] = None) -> dict:
        """Delete a file from the repo.

        DELETE /api/v1/agents/{path}/{name}/repo/file
        """
        delete_url = f"{self.server}/api/v1/agents/{path}/{name}/repo/file"
        body = {
            "branch": revision,
            "file_path": file_path,
            "commit_message": commit_message or f"Delete {file_path}",
        }
        try:
            return self._openapi._request("DELETE", url=delete_url, json_body=body)
        except HubError as exc:
            raise _wrap(exc) from exc
