# Copyright (c) ModelScope Contributors. All rights reserved.
"""Minimal HTTP client over ultron's auth + agent-repository API.

Uses the standard library only (``urllib``) so the CLI has no extra
dependencies. It speaks the same endpoints the dashboard and the
``/api/v1/agents/*`` repository contract expose:

* ``POST /auth/login``                                  -> token
* ``GET  /api/v1/agents/{path}/{name}``                 -> repo exists?
* ``POST /api/v1/agents``                               -> create repo
* ``POST /api/v1/repos/agents/{path}/{name}/commit/master`` -> upload files
"""
import json
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

    # ---- auth ----

    def login(self, username: str, password: str) -> str:
        resp = self._request(
            "POST", "/auth/login", {"username": username, "password": password}
        )
        return resp["data"]["token"]

    # ---- repository ----

    def check_repo(self, path: str, name: str) -> bool:
        """True if the repo exists, False on 404."""
        try:
            self._request("GET", f"/api/v1/agents/{path}/{name}")
            return True
        except ApiError as e:
            if e.status == 404:
                return False
            raise

    def create_repo(self, path: str, name: str, framework: str) -> dict:
        return self._request(
            "POST",
            "/api/v1/agents",
            {"Path": path, "Name": name, "Framework": framework},
        )

    def commit(
        self, path: str, name: str, actions: List[dict], message: str
    ) -> dict:
        return self._request(
            "POST",
            f"/api/v1/repos/agents/{path}/{name}/commit/master",
            {"commit_message": message, "actions": actions},
        )


def _extract_detail(e: "urllib.error.HTTPError") -> str:
    try:
        payload = json.loads(e.read().decode("utf-8"))
        return payload.get("detail") or payload.get("message") or str(payload)
    except Exception:
        return e.reason or "request failed"
