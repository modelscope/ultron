# Copyright (c) ModelScope Contributors. All rights reserved.
"""HTTP client for ultron's agent-repository API.

All endpoints go through ``/openapi/v1/`` via ``modelscope_hub.OpenAPIClient``:

* ``GET  /openapi/v1/users/me``                            → login
* ``GET  /openapi/v1/agents/{path}/{name}``                → repo metadata
* ``POST /openapi/v1/agents``                              → create/update agent
* ``GET  /openapi/v1/agents/{path}/{name}/repo/files``     → list files
* ``GET  /openapi/v1/agents/{path}/{name}/repo``           → file download
* ``POST /openapi/v1/files/upload``                        → upload zip
"""
import io
from dataclasses import dataclass
from typing import Dict, List, Optional, Union

import requests
from modelscope_hub._openapi import OpenAPIClient
from modelscope_hub.config import HubConfig
from modelscope_hub.errors import HubError, NotExistError

from .sync import zip_resources


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
        """All file paths in the repo, recursing into sub-directories.

        The server returns ``{"commit": {...}, "trees": [...]}`` where each
        entry has ``type`` ("tree" for dirs, "blob" for files) and ``path``.
        """
        all_files: List[str] = []
        try:
            data = self._openapi._request(
                "GET", f"/agents/{path}/{name}/repo/files",
                params={
                    "recursive": "true",
                    "page_size": "100",
                    "page_number": "1",
                    "revision": revision,
                },
            )
            trees = []
            if isinstance(data, dict):
                trees = data.get("trees") or data.get("Trees") or []
            elif isinstance(data, list):
                trees = data
            for item in trees:
                if not isinstance(item, dict):
                    continue
                item_path = item.get("path") or item.get("Path") or ""
                item_type = item.get("type") or item.get("Type") or ""
                if item_type == "blob" and item_path:
                    all_files.append(item_path)
        except HubError as exc:
            raise _wrap(exc) from exc
        return all_files

    def list_repo_files_detail(self, path: str, name: str, revision: str = 'master') -> List[RemoteFileInfo]:
        """All blob files with sha256 and committed_date.

        Returns a list of ``RemoteFileInfo`` for each blob entry in the repo.
        Raises ``ApiError(404, ...)`` if the repo does not exist.
        """
        results: List[RemoteFileInfo] = []
        try:
            data = self._openapi._request(
                "GET", f"/agents/{path}/{name}/repo/files",
                params={
                    "recursive": "true",
                    "page_size": "100",
                    "page_number": "1",
                    "revision": revision,
                },
            )
            trees = []
            if isinstance(data, dict):
                trees = data.get("trees") or data.get("Trees") or []
            elif isinstance(data, list):
                trees = data
            for item in trees:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type") or item.get("Type") or ""
                if item_type != "blob":
                    continue
                item_path = item.get("path") or item.get("Path") or ""
                item_sha = item.get("sha256") or item.get("Sha256") or ""
                item_date = item.get("committed_date") or item.get("Committed_date") or 0
                if item_path:
                    results.append(RemoteFileInfo(
                        path=item_path, sha256=item_sha, committed_date=int(item_date),
                    ))
        except HubError as exc:
            raise _wrap(exc) from exc
        return results

    def download_repo_file(self, path: str, name: str, file_path: str,
                           revision: str = "master") -> str:
        """Download one repo file (GET /agents/{path}/{name}/resolve/{revision}/{file_path}).

        This endpoint does NOT use the /openapi/v1/ prefix.
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
        return resp.text

    # ---- upload ----

    def upload_file(self, resources: Union[Dict[str, str], bytes]) -> str:
        """Upload agent files (POST /files/upload), return the file ID.

        Args:
            resources: Either a dict {rel_path: content} that will be zipped,
                       or raw zip bytes.
        """
        if isinstance(resources, dict):
            zip_bytes = zip_resources(resources)
        else:
            zip_bytes = resources
        try:
            files = [("file", ("agent.zip", io.BytesIO(zip_bytes), "application/zip"))]
            result = self._openapi._request("POST", "/files/upload", files=files)
            return (
                result.get("id")
                or result.get("Id")
                or result.get("file_id")
                or ""
            )
        except HubError as exc:
            raise _wrap(exc) from exc
