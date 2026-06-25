# Copyright (c) ModelScope Contributors. All rights reserved.
"""File watcher (polling) and daemon management for ``ultron watch``."""
import logging
import os
import signal
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler
from typing import List, Optional

from .cache import load_sync_state, log_file, pid_file, save_sync_state
from .client import ApiError
from .sync import (
    backup_local,
    detect_local_changes,
    pull_incremental,
    push_resources,
)

_logger: Optional[logging.Logger] = None


def _get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    _logger = logging.getLogger("ultron.watch")
    _logger.setLevel(logging.INFO)
    fh = RotatingFileHandler(
        str(log_file()), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
    _logger.addHandler(fh)
    return _logger


def watch_loop(spec, client, username: str, name: str, framework: str, interval: int = 60, *, push_only: bool = True):
    """Sync loop: push local changes, optionally pull remote changes.

    push_only=True (default): only pushes, never modifies local files.
    push_only=False: full bidirectional sync (remote wins on conflict).
    """
    logger = _get_logger()
    logger.info("Watch started for %s/%s (root=%s, interval=%ds, push_only=%s)",
                username, name, spec.workspace_root, interval, push_only)

    state = load_sync_state(name)
    running = True

    def _handle_term(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _handle_term)
    signal.signal(signal.SIGINT, _handle_term)

    while running:
        time.sleep(interval)
        if not running:
            break

        # ---- Fetch remote file list ----
        try:
            remote_files = client.list_repo_files_detail(username, name)
        except ApiError as e:
            if e.status in (404, 500):
                remote_files = []
            else:
                logger.error("Failed to list remote files: %s", e)
                continue

        # ---- Collect local resources & detect changes ----
        local_resources = spec.collect()
        scope = set(local_resources.keys()) | set(state.get("remote_files", {}).keys())
        remote_sha_map = {f.path: f.sha256 for f in remote_files if f.path in scope}

        remote_changed = (
            max((f.committed_date for f in remote_files), default=0) > state["last_commit_date"]
            or set(remote_sha_map.keys()) != set(state.get("remote_files", {}).keys())
        )
        local_changed = bool(detect_local_changes(local_resources, state["remote_files"]))

        # ---- Sync decision ----
        did_sync = False
        try:
            did_sync = _sync_action(
                push_only, remote_changed, local_changed,
                client, username, name, framework, spec,
                remote_files, local_resources, logger,
            )
        except Exception as exc:
            logger.error("Sync failed (will retry): %s", exc)

        # ---- Update baseline on successful sync ----
        if did_sync:
            _refresh_baseline(client, username, name, spec, state, logger)
            save_sync_state(name, state["last_commit_date"], state["remote_files"])

    logger.info("Watch stopped (signal received).")
    pf = pid_file()
    if pf.exists():
        pf.unlink(missing_ok=True)


def _sync_action(
    push_only, remote_changed, local_changed,
    client, username, name, framework, spec,
    remote_files, local_resources, logger,
) -> bool:
    """Execute the appropriate sync action. Returns True if something changed."""
    if push_only:
        if not local_changed:
            return False
        push_resources(client, username, name, framework, local_resources)
        logger.info("Pushed local changes.")
        return True

    if remote_changed and local_changed:
        backup_path = backup_local(spec, name)
        pull_incremental(client, username, name, spec, remote_files, local_resources)
        logger.warning("Conflict: remote wins. Local backup: %s", backup_path)
    elif remote_changed:
        backup_path = backup_local(spec, name)
        pull_incremental(client, username, name, spec, remote_files, local_resources)
        logger.info("Pulled remote changes (backup: %s).", backup_path)
    elif local_changed:
        push_resources(client, username, name, framework, local_resources)
        logger.info("Pushed local changes.")
    else:
        return False
    return True


def _refresh_baseline(client, username: str, name: str, spec, state: dict, logger) -> None:
    """Re-fetch remote file list and update state in-place."""
    for attempt in range(3):
        try:
            fresh = client.list_repo_files_detail(username, name)
            managed = set(spec.collect().keys())
            state["last_commit_date"] = max((f.committed_date for f in fresh), default=0)
            state["remote_files"] = {f.path: f.sha256 for f in fresh if f.path in managed}
            return
        except ApiError as e:
            if e.status == 500 and attempt < 2:
                time.sleep(3)
                continue
            logger.error("Failed to refresh baseline: %s", e)
            return
        except Exception as exc:
            logger.error("Failed to refresh baseline: %s", exc)
            return


def daemonize(target, *args, **kwargs):
    """Double-fork to daemonize *target* on Unix.

    Writes the daemon PID to the pid file so ``ultron stop`` can find it.
    """
    pf = pid_file()

    pid = os.fork()
    if pid > 0:
        return  # Parent returns immediately.

    os.setsid()

    pid = os.fork()
    if pid > 0:
        os._exit(0)  # First child exits; grandchild is the actual daemon.

    # Grandchild: write PID and redirect stdio.
    pf.write_text(str(os.getpid()), encoding="utf-8")

    sys.stdout.flush()
    sys.stderr.flush()
    with open(os.devnull, "r") as devnull:
        os.dup2(devnull.fileno(), sys.stdin.fileno())
    log_fd = os.open(str(log_file()), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(log_fd, sys.stdout.fileno())
    os.dup2(log_fd, sys.stderr.fileno())
    os.close(log_fd)

    try:
        target(*args, **kwargs)
    finally:
        pf.unlink(missing_ok=True)
        os._exit(0)


def stop_daemon() -> bool:
    """Stop ALL running watch daemon processes.

    Kills the PID-file-tracked process, then scans for orphaned processes.
    Waits briefly for graceful shutdown before returning.
    """
    stopped = False
    pf = pid_file()

    # 1. Kill PID-file-tracked process.
    tracked_pid = None
    if pf.exists():
        try:
            tracked_pid = int(pf.read_text().strip())
            os.kill(tracked_pid, signal.SIGTERM)
            stopped = True
        except (ValueError, OSError, ProcessLookupError):
            tracked_pid = None
        pf.unlink(missing_ok=True)

    # 2. Kill orphaned watch processes.
    my_pid = os.getpid()
    for found_pid in _find_watch_pids():
        if found_pid in (my_pid, tracked_pid):
            continue
        try:
            os.kill(found_pid, signal.SIGTERM)
            stopped = True
        except (ProcessLookupError, PermissionError):
            pass

    # 3. Wait for processes to exit (up to 3s).
    if stopped:
        time.sleep(1)

    return stopped


def _find_watch_pids() -> List[int]:
    """Find PIDs of running 'ultron watch' daemon processes via pgrep."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "ultron watch --framework"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return [int(p) for p in result.stdout.strip().split("\n") if p.strip().isdigit()]
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return []
