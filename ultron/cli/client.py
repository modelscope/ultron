# Copyright (c) ModelScope Contributors. All rights reserved.
"""HTTP client for ultron's agent-repository API.

Delegates entirely to ``modelscope_hub``'s ``OpenAPIClient``
(``/openapi/v1/`` endpoints). All requests go through the OpenAPI surface.

Endpoints used:

* ``GET  /openapi/v1/users/me``                            → whoami (login)
* ``GET  /openapi/v1/agents/{path}/{name}``                → repo metadata
* ``POST /openapi/v1/agents``                              → create/update agent
* ``GET  /openapi/v1/agents/{path}/{name}/repo/files``     → list files
* ``GET  /openapi/v1/agents/{path}/{name}/repo``           → file download
* ``POST /openapi/v1/files/upload``                        → upload zip
"""
import io
from typing import List, Optional

from modelscope_hub._openapi import OpenAPIClient
from modelscope_hub.config import HubConfig
from modelscope_hub.errors import HubError, NotExistError


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

    def list_repo_files(self, path: str, name: str) -> List[str]:
        """All file paths in the repo (follows pagination)."""
        all_files: List[str] = []
        page = 1
        page_size = 100
        while True:
            try:
                data = self._openapi._request(
                    "GET", f"/agents/{path}/{name}/repo/files",
                    params={
                        "Recursive": "true",
                        "PageNumber": str(page),
                        "PageSize": str(page_size),
                    },
                )
            except HubError as exc:
                raise _wrap(exc) from exc
            # Normalize: response may be a list of dicts or wrapped in {"Files": [...]}
            if isinstance(data, list):
                files = data
                total = len(data)
            elif isinstance(data, dict):
                files = data.get("Files") or data.get("files") or []
                total = data.get("Total") or data.get("total") or len(files)
            else:
                break
            for f in files:
                if isinstance(f, str):
                    all_files.append(f)
                elif isinstance(f, dict):
                    p = f.get("Path") or f.get("path") or f.get("Name") or f.get("name", "")
                    if p:
                        all_files.append(p)
            if page * page_size >= total:
                break
            page += 1
        return all_files

    def download_repo_file(self, path: str, name: str, file_path: str) -> str:
        """Download one repo file, decoded to UTF-8 text."""
        try:
            data = self._openapi._request(
                "GET",
                f"/agents/{path}/{name}/repo",
                params={"FilePath": file_path},
                unwrap=False,
            )
            # Response may be raw text/bytes or JSON-wrapped content.
            if isinstance(data, (bytes, bytearray)):
                return data.decode("utf-8")
            if isinstance(data, str):
                return data
            # If JSON envelope, try extracting content.
            if isinstance(data, dict):
                return data.get("content", data.get("Content", str(data)))
            return str(data)
        except HubError as exc:
            raise _wrap(exc) from exc

    # ---- upload ----

    def upload_file(self, zip_bytes: bytes) -> str:
        """Upload a zip file (POST /files/upload), return the file ID."""
        try:
            file_obj = io.BytesIO(zip_bytes)
            result = self._openapi.upload_file(file=file_obj)
            return (
                result.get("id")
                or result.get("Id")
                or result.get("file_id")
                or ""
            )
        except HubError as exc:
            raise _wrap(exc) from exc
