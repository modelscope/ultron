# Copyright (c) ModelScope Contributors. All rights reserved.
"""CLI configuration: server URL + auth token persistence.

State is stored in ``~/.ultron/cli.json`` (mode 600), next to the rest of
ultron's per-user data (``ultron/config.py`` uses the same ``~/.ultron``
directory). Environment variables ``ULTRON_SERVER`` and ``ULTRON_TOKEN`` take
precedence over the stored values so the CLI works in CI without a login step.
"""
import json
import os
from pathlib import Path
from typing import Optional


def _config_path() -> Path:
    data_dir = os.environ.get("ULTRON_DATA_DIR", "").strip() or "~/.ultron"
    return Path(os.path.expanduser(data_dir)) / "cli.json"


def load() -> dict:
    """Load the stored CLI config, or an empty dict if none exists."""
    path = _config_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(server: str, username: str, token: str) -> Path:
    """Persist credentials to ``~/.ultron/cli.json`` with 0600 permissions."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"server": server, "username": username, "token": token}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def resolve_server(override: Optional[str] = None) -> Optional[str]:
    """Server URL precedence: explicit flag > ULTRON_SERVER env > stored config."""
    if override:
        return override.rstrip("/")
    env = os.environ.get("ULTRON_SERVER", "").strip()
    if env:
        return env.rstrip("/")
    server = load().get("server")
    return server.rstrip("/") if server else None


def resolve_token(override: Optional[str] = None) -> Optional[str]:
    """Token precedence: explicit flag > ULTRON_TOKEN env > stored config."""
    if override:
        return override
    env = os.environ.get("ULTRON_TOKEN", "").strip()
    if env:
        return env
    return load().get("token")


def resolve_username() -> Optional[str]:
    """Stored username (the repo ``Path`` for uploads), if logged in."""
    return load().get("username")
