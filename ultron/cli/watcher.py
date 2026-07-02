# Copyright (c) ModelScope Contributors. All rights reserved.
"""File watcher (polling) and daemon management for ``ultron watch``."""
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from typing import List, Optional

from .cache import load_sync_state, log_file, pid_file, save_sync_state, stop_file
from .client import ApiError
from .sync import (
    backup_local,
    detect_local_changes,
    pull_incremental,
    push_incremental,
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


def watch_loop(spec, client, username: str, repo: str, framework: str, interval: int = 120, *, push_only: bool = True):
    """Sync loop: push local changes, optionally pull remote changes.

    Args:
        repo: Remote repository name (used as the API path component).
        push_only: True (default) = only pushes, never modifies local files.
                   False = full bidirectional sync (remote wins on conflict).
    """
    logger = _get_logger()
    logger.info("Watch started for %s/%s (root=%s, interval=%ds, push_only=%s)",
                username, repo, spec.workspace_root, interval, push_only)

    state = load_sync_state(repo)
    running = True
    stop_event = threading.Event()
    sf = stop_file()

    def _handle_term(signum, frame):
        nonlocal running
        running = False
        stop_event.set()

    # Unix: register signal handlers for graceful stop via kill(1).
    # Windows: SIGTERM triggers TerminateProcess (hard kill), so signals are
    # unreliable; the stop-file mechanism below is the primary channel.
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_term)
    signal.signal(signal.SIGINT, _handle_term)

    # Remove any stale stop file from a previous session.
    sf.unlink(missing_ok=True)

    while running:
        # Wait with periodic wake-ups to poll the stop file (Windows compat).
        # On Unix, the signal handler sets stop_event immediately.
        elapsed = 0
        poll_interval = min(interval, 5)  # check stop file every 5s
        while elapsed < interval and running:
            stop_event.wait(timeout=poll_interval)
            if stop_event.is_set():
                running = False
                break
            if sf.exists():
                running = False
                break
            elapsed += poll_interval
        if not running:
            break

        # ---- Fetch remote file list ----
        try:
            remote_files = client.list_repo_files_detail(username, repo)
        except ApiError as e:
            if e.status in (404, 500):
                remote_files = []
            else:
                logger.error("Failed to list remote files: %s", e)
                continue

        # ---- Collect local resources & detect changes ----
        local_resources = spec.collect_bytes()
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
                client, username, repo, framework, spec,
                remote_files, local_resources, logger,
                state,
            )
        except Exception as exc:
            logger.error("Sync failed (will retry): %s", exc)

        # ---- Update baseline on successful sync ----
        if did_sync:
            # After a pull, local files may have changed — re-collect.
            if not push_only:
                local_resources = spec.collect_bytes()
            _refresh_baseline(client, username, repo, local_resources, state, logger)
            save_sync_state(repo, state["last_commit_date"], state["remote_files"])

    logger.info("Watch stopped (signal received).")
    pf = pid_file()
    if pf.exists():
        pf.unlink(missing_ok=True)
    sf.unlink(missing_ok=True)


def _push_local(client, username, name, framework, local_resources, state, logger) -> bool:
    """Push local changes: full upload on first time, incremental thereafter.

    Returns True if something was actually pushed, False otherwise.
    """
    if not local_resources:
        logger.debug("No local resources to push — skipping.")
        return False
    if not state.get("remote_files"):
        push_resources(client, username, name, framework, local_resources)
        logger.info("Pushed local changes (full upload — first time).")
        return True
    else:
        changed = detect_local_changes(local_resources, state["remote_files"])
        if changed:
            push_incremental(client, username, name, changed, set(state["remote_files"].keys()))
            logger.info("Pushed local changes (incremental commit).")
            return True
        return False


def _sync_action(
    push_only, remote_changed, local_changed,
    client, username, name, framework, spec,
    remote_files, local_resources, logger,
    state,
) -> bool:
    """Execute the appropriate sync action. Returns True if something changed."""
    if push_only:
        if not local_changed:
            return False
        return _push_local(client, username, name, framework, local_resources, state, logger)

    if remote_changed and local_changed:
        backup_path = backup_local(spec, name)
        pull_incremental(client, username, name, spec, remote_files, local_resources)
        logger.warning("Conflict: remote wins. Local backup: %s", backup_path)
    elif remote_changed:
        backup_path = backup_local(spec, name)
        pull_incremental(client, username, name, spec, remote_files, local_resources)
        logger.info("Pulled remote changes (backup: %s).", backup_path)
    elif local_changed:
        _push_local(client, username, name, framework, local_resources, state, logger)
    else:
        return False
    return True


def _refresh_baseline(client, username: str, name: str, local_resources: dict, state: dict, logger) -> None:
    """Re-fetch remote file list and update state in-place.

    Uses *local_resources* keys as the managed-file scope to avoid a redundant
    disk scan (caller already collected them this cycle).
    """
    managed = set(local_resources.keys())
    for attempt in range(3):
        try:
            fresh = client.list_repo_files_detail(username, name)
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
    """Launch *target* as a background process.

    Unix: classic double-fork.
    Windows: subprocess.Popen with DETACHED_PROCESS.
    """
    if hasattr(os, "fork"):
        _daemonize_unix(target, *args, **kwargs)
    else:
        _daemonize_windows(target, *args, **kwargs)


def _daemonize_unix(target, *args, **kwargs):
    """Double-fork daemon (Unix only)."""
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


def _daemonize_windows(target, *args, **kwargs):
    """Spawn a detached background process (Windows).

    Re-launches Python with ``ultron _watch_daemon`` internal command,
    passing serialized arguments via a temp JSON file.
    """
    import json
    import tempfile

    # Serialize the arguments that watch_loop needs.
    # spec (args[0]) carries the agent_name used to build the allowlist scope.
    # client (args[1]) carries server/token for the child process.
    spec_obj = args[0] if len(args) > 0 else None
    client_obj = args[1] if len(args) > 1 else None
    payload = {
        "username": args[2] if len(args) > 2 else kwargs.get("username", ""),
        "repo": args[3] if len(args) > 3 else kwargs.get("repo", ""),
        "framework": args[4] if len(args) > 4 else kwargs.get("framework", ""),
        "interval": args[5] if len(args) > 5 else kwargs.get("interval", 120),
        "push_only": kwargs.get("push_only", True),
        "local_name": getattr(spec_obj, "agent_name", "") if spec_obj else "",
        "server": getattr(client_obj, "server", "") if client_obj else "",
        "token": getattr(client_obj, "token", "") if client_obj else "",
        # spec and client are rebuilt in the child from stored config.
    }
    # Write to a temp file that the child will read and delete.
    fd, param_path = tempfile.mkstemp(suffix=".json", prefix="ultron_watch_")
    with os.fdopen(fd, "w") as f:
        json.dump(payload, f)

    # Launch detached subprocess.
    CREATE_NO_WINDOW = 0x08000000
    DETACHED_PROCESS = 0x00000008
    proc = subprocess.Popen(
        [sys.executable, "-m", "ultron.cli", "_watch_daemon", param_path],
        creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
        close_fds=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    # Write PID file.
    pf = pid_file()
    pf.write_text(str(proc.pid), encoding="utf-8")


_DEFAULT_WATCH_PATTERNS = [
    "ultron watch --framework",
]


def stop_daemon(extra_patterns: Optional[List[str]] = None) -> bool:
    """Stop ALL running watch daemon processes (cross-platform).

    Primary mechanism: write a stop-file that the watch loop polls.
    Secondary: send SIGTERM (Unix) or taskkill (Windows) as a backup.
    Cleans up PID file and stop file on return.
    """
    stopped = False
    pf = pid_file()
    sf = stop_file()

    # 1. Write the stop file — the watch loop will notice within 5 seconds.
    sf.write_text("stop", encoding="utf-8")

    # 2. Also send SIGTERM to PID-tracked process (Unix only).
    # On Windows, os.kill(SIGTERM) = TerminateProcess (hard kill), which
    # bypasses graceful shutdown entirely.  Rely on stop-file instead.
    tracked_pid = None
    if pf.exists():
        try:
            tracked_pid = int(pf.read_text().strip())
            if hasattr(os, "fork"):
                # Unix: SIGTERM triggers the handler → sets running=False.
                os.kill(tracked_pid, signal.SIGTERM)
            # On Windows, the stop file (written above) is the sole signal.
            stopped = True
        except (ValueError, OSError, ProcessLookupError):
            tracked_pid = None

    # 3. Kill orphaned watch processes.
    if hasattr(os, "fork"):
        # Unix: use pgrep.
        my_pid = os.getpid()
        for found_pid in _find_watch_pids(extra_patterns):
            if found_pid in (my_pid, tracked_pid):
                continue
            try:
                os.kill(found_pid, signal.SIGTERM)
                stopped = True
            except (ProcessLookupError, PermissionError):
                pass
    else:
        # Windows: use wmic/tasklist to find orphaned processes.
        for found_pid in _find_watch_pids_windows(extra_patterns):
            if found_pid == tracked_pid:
                continue
            _terminate_pid_windows(found_pid)
            stopped = True

    # 4. Wait for graceful exit (stop-file polling interval is 5s max).
    if stopped or tracked_pid:
        _wait_for_exit(tracked_pid, timeout=8)

    # 5. Force kill if still alive.
    if tracked_pid and _is_alive(tracked_pid):
        _force_kill(tracked_pid)

    # 6. Clean up.
    pf.unlink(missing_ok=True)
    sf.unlink(missing_ok=True)

    return stopped or tracked_pid is not None


def _find_watch_pids(extra_patterns: Optional[List[str]] = None) -> List[int]:
    """Find PIDs of running watch daemon processes via pgrep (Unix only).

    Searches default patterns plus any *extra_patterns* provided by the caller.
    """
    patterns = list(dict.fromkeys(_DEFAULT_WATCH_PATTERNS + (extra_patterns or [])))
    pids: set = set()
    for pattern in patterns:
        try:
            result = subprocess.run(
                ["pgrep", "-f", "--", pattern],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                for p in result.stdout.strip().split("\n"):
                    if p.strip().isdigit():
                        pids.add(int(p.strip()))
        except (OSError, subprocess.TimeoutExpired, ValueError):
            pass
    return list(pids)


def _find_watch_pids_windows(extra_patterns: Optional[List[str]] = None) -> List[int]:
    """Find PIDs of running watch daemon processes on Windows via wmic/tasklist.

    Searches for python processes whose command line matches watch patterns.
    """
    patterns = list(dict.fromkeys(_DEFAULT_WATCH_PATTERNS + (extra_patterns or [])))
    pids: set = set()
    try:
        # Use wmic to get process command lines.
        result = subprocess.run(
            ["wmic", "process", "where", "name like '%python%'",
             "get", "processid,commandline"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []
        for line in result.stdout.splitlines():
            line_lower = line.lower()
            for pattern in patterns:
                if pattern.lower() in line_lower:
                    # Extract PID (last number on the line).
                    parts = line.strip().split()
                    if parts and parts[-1].isdigit():
                        pids.add(int(parts[-1]))
                    break
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return list(pids)


def _terminate_pid_windows(pid: int) -> None:
    """Terminate a process on Windows using taskkill."""
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _is_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def _wait_for_exit(pid: Optional[int], timeout: int = 8) -> None:
    """Wait up to *timeout* seconds for a process to exit."""
    if pid is None:
        time.sleep(2)
        return
    for _ in range(timeout * 2):  # check every 0.5s
        if not _is_alive(pid):
            return
        time.sleep(0.5)


def _force_kill(pid: int) -> None:
    """Force-kill a process (SIGKILL on Unix, taskkill /F on Windows)."""
    if hasattr(os, "fork"):
        try:
            os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
        except (ProcessLookupError, PermissionError, OSError):
            pass
    else:
        _terminate_pid_windows(pid)
