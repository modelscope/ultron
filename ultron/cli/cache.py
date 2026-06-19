# Copyright (c) ModelScope Contributors. All rights reserved.
"""ULTRON_CACHE path helpers.

Cache layout (under ``~/.ultron/cache/``):

::

    cache/
    ├── {name}_{timestamp}.zip   # local backups
    ├── cloud/{name}/            # downloaded cloud copies
    ├── logs/watch.log           # runtime logs
    └── watch.pid                # background process PID
"""
import os
from pathlib import Path


def _ultron_home() -> Path:
    data_dir = os.environ.get("ULTRON_DATA_DIR", "").strip() or "~/.ultron"
    return Path(os.path.expanduser(data_dir))


def cache_dir() -> Path:
    """Root cache directory: ``~/.ultron/cache/``."""
    d = _ultron_home() / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cloud_dir(name: str) -> Path:
    """Cloud download directory for a given agent: ``~/.ultron/cache/cloud/{name}/``."""
    d = cache_dir() / "cloud" / name
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
