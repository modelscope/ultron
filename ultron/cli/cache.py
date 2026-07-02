# Copyright (c) ModelScope Contributors. All rights reserved.
"""ULTRON_CACHE path helpers.

Cache layout (under ``~/.ultron/cache/``):

::

    cache/
    ├── {name}_{timestamp}.zip   # local backups
    ├── sync_{name}.json         # bidirectional sync baseline
    ├── logs/watch.log           # runtime logs
    └── watch.pid                # background process PID
"""
import json
import os
from pathlib import Path
from typing import Dict


def _ultron_home() -> Path:
    data_dir = os.environ.get("ULTRON_DATA_DIR", "").strip() or "~/.ultron"
    return Path(os.path.expanduser(data_dir))


def cache_dir() -> Path:
    """Root cache directory: ``~/.ultron/cache/``."""
    d = _ultron_home() / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_file() -> Path:
    """Log file path: ``~/.ultron/cache/logs/watch.log``."""
    d = cache_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d / "watch.log"


def pid_file() -> Path:
    """PID file for the background watch process."""
    return cache_dir() / "watch.pid"


def stop_file() -> Path:
    """Stop signal file: presence tells the watch loop to exit gracefully.

    Cross-platform mechanism — works on both Unix and Windows where signal
    delivery is unreliable.
    """
    return cache_dir() / "watch.stop"


# ---- Sync state persistence ----

def sync_state_file(name: str) -> Path:
    """Sync state file: ``~/.ultron/cache/sync_{name}.json``."""
    return cache_dir() / f"sync_{name}.json"


def load_sync_state(name: str) -> dict:
    """Load sync state from disk.

    Returns ``{"last_commit_date": 0, "remote_files": {}}``
    if the file does not exist or is corrupted.
    """
    default: dict = {"last_commit_date": 0, "remote_files": {}}
    path = sync_state_file(name)
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return default
        data.setdefault("last_commit_date", 0)
        data.setdefault("remote_files", {})
        # Drop legacy field if present.
        data.pop("local_files", None)
        return data
    except (json.JSONDecodeError, OSError):
        return default


def save_sync_state(name: str, last_commit_date: int, remote_files: Dict[str, str]) -> None:
    """Persist sync state to disk (atomic write)."""
    path = sync_state_file(name)
    tmp = path.with_suffix(".tmp")
    payload = json.dumps(
        {
            "last_commit_date": last_commit_date,
            "remote_files": remote_files,
        },
        ensure_ascii=False, indent=2,
    )
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)

