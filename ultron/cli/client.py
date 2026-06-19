# Copyright (c) ModelScope Contributors. All rights reserved.
"""HTTP client for ultron's agent-repository API.

Delegates to ``modelscope_hub``'s ``LegacyClient`` (``/api/v1/`` endpoints)
and ``OpenAPIClient`` (``/openapi/v1/`` endpoints) wherever possible.
The upload flow follows the two-step protocol:

1. ``POST /openapi/v1/files/upload``  → obtain a file ID
2. ``POST /openapi/v1/agents``        → create/update agent with the file ID

Endpoints handled via LegacyClient (repo_type="agent" → path segment "agents"):

* ``POST /api/v1/login``                               → token validation
* ``GET  /api/v1/agents/{path}/{name}``                → repo metadata
* ``POST /api/v1/agents``                              → create repo
* ``GET  /api/v1/agents/{path}/{name}/repo/files``     → list files
* ``GET  /api/v1/agents/{path}/{name}/repo``           → file download
"""
import io
from typing import List, Optional

from modelscope_hub._legacy_api import LegacyClient
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
        self._legacy = LegacyClient(
            token=token, endpoint=self.server, timeout=timeout
        )
        self._config = HubConfig(endpoint=self.server, token=token)
        self._openapi = OpenAPIClient(config=self._config, timeout=float(timeout))

    # ---- auth ----

    def login(self, token: str) -> str:
        """Validate token via POST /api/v1/login, return username."""
        try:
            data, _ = self._legacy.login(token)
        except HubError as exc:
            raise _wrap(exc) from exc
        # Update internal state with the validated token.
        self.token = token
        self._legacy.token = token
        self._config.token = token
        return data.get("Username", data.get("username", ""))

    # ---- repository ----

    def repo_info(self, path: str, name: str) -> Optional[dict]:
        """Repo metadata or None if the repo does not exist (404)."""
        try:
            return self._legacy.get_repo_info(f"{path}/{name}", "agent")
        except NotExistError:
            return None
        except HubError as exc:
            raise _wrap(exc) from exc

    def check_repo(self, path: str, name: str) -> bool:
        """True if the repo exists, False on 404."""
        return self.repo_info(path, name) is not None

    def create_repo(self, path: str, name: str, framework: str) -> dict:
        try:
            return self._legacy.create_repo("agent", {
                "Path": path,
                "Name": name,
                "Framework": framework,
                "Visibility": "public",
            })
        except HubError as exc:
            raise _wrap(exc) from exc

    def list_repo_files(self, path: str, name: str) -> List[str]:
        """All file paths in the repo."""
        try:
            files = self._legacy.list_repo_files(f"{path}/{name}", "agent")
        except HubError as exc:
            raise _wrap(exc) from exc
        # list_repo_files returns list[dict] with "Path" or "Name" keys.
        result: List[str] = []
        for f in files:
            p = f.get("Path") or f.get("path") or f.get("Name") or f.get("name", "")
            if p:
                result.append(p)
        return result

    def download_repo_file(self, path: str, name: str, file_path: str) -> str:
        """Download one repo file, decoded to UTF-8 text."""
        try:
            resp = self._legacy.download_stream(
                f"{path}/{name}", "agent", file_path
            )
            return resp.text
        except HubError as exc:
            raise _wrap(exc) from exc

    # ---- upload (two-step protocol) ----

    def upload_zip(
        self,
        path: str,
        name: str,
        framework: str,
        zip_bytes: bytes,
        message: str,
    ) -> dict:
        """Upload a zip snapshot and create/update the agent.

        Step 1: POST /openapi/v1/files/upload  → file ID
        Step 2: POST /openapi/v1/agents        → create/update agent
        """
        try:
            # Step 1: upload zip file, obtain the file ID.
            file_obj = io.BytesIO(zip_bytes)
            result = self._openapi.upload_file(file=file_obj)
            file_id = (
                result.get("id")
                or result.get("Id")
                or result.get("file_id")
                or ""
            )
            # Step 2: create/update agent with the uploaded file ID.
            agent_data = self._openapi._request(
                "POST",
                "/agents",
                json_body={
                    "name": name,
                    "path": path,
                    "system_prompt_files": file_id,
                },
            )
            return {"data": agent_data} if isinstance(agent_data, dict) else {"data": {}}
        except HubError as exc:
            raise _wrap(exc) from exc
