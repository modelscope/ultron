# Copyright (c) ModelScope Contributors. All rights reserved.
"""File watcher (polling) and daemon management for ``ultron watch``."""
import logging
import os
import signal
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Optional

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
    # File handler (rotated at 5 MB, keep 3 backups).
    fh = RotatingFileHandler(
        str(log_file()), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
    _logger.addHandler(fh)
    return _logger


def watch_loop(spec, client, username: str, name: str, framework: str, interval: int = 60, sessions_dir: str = None):
    """Bidirectional sync loop: pull remote changes, push local changes.

    Runs indefinitely until SIGTERM/SIGINT is received.
    If *sessions_dir* is provided and a valid LLM API key is configured, also runs the
    local memory/skill extraction pipeline periodically.
    """
    logger = _get_logger()
    root: Path = spec.workspace_root
    logger.info("Watch started for %s/%s (root=%s, interval=%ds)", username, name, root, interval)

    # Load sync baseline from cache.
    state = load_sync_state(name)

    # Optional: local pipeline (requires ULTRON_API_KEY or equivalent)
    local_ultron = None
    if sessions_dir:
        try:
            from ultron import Ultron, load_ultron_dotenv
            load_ultron_dotenv()
            local_ultron = Ultron()
            if not local_ultron.llm_service.is_available:
                logger.info("Local pipeline skipped: no LLM API key configured")
                local_ultron = None
            else:
                logger.info("Local pipeline enabled (sessions_dir=%s)", sessions_dir)
        except Exception as exc:
            logger.warning("Local pipeline init failed (skipped): %s", exc)
            local_ultron = None

    running = True
    # Run pipeline every N poll cycles (e.g. 5 * 60s = ~5 min)
    pipeline_every_n_cycles = 5
    cycle_counter = 0
    sessions_dirty = True  # run once at start to catch up
    last_sessions_mtime = 0.0

    def _handle_term(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _handle_term)
    signal.signal(signal.SIGINT, _handle_term)

    while running:
        time.sleep(interval)
        if not running:
            break

        # ---- Step 1: Fetch remote file list ----
        try:
            remote_files = client.list_repo_files_detail(username, name)
        except ApiError as e:
            if e.status in (404, 500):
                # 404 = repo doesn't exist yet; 500 = newly created repo not ready.
                remote_files = []
            else:
                logger.error("Failed to list remote files: %s", e)
                continue

        remote_max_date = max((f.committed_date for f in remote_files), default=0)
        remote_sha_map = {f.path: f.sha256 for f in remote_files}

        # ---- Step 2: Detect remote changes ----
        # Two signals: (a) timestamp advanced, or (b) file set changed (covers
        # pure deletions where no remaining file's committed_date advances).
        remote_changed = (
            (remote_max_date > state["last_commit_date"])
            or (set(remote_sha_map.keys()) != set(state.get("remote_files", {}).keys()))
        )

        # ---- Step 3: Collect local and detect local changes ----
        local_resources = spec.collect()
        local_changes = detect_local_changes(local_resources, state["remote_files"])
        local_changed = bool(local_changes)

        # ---- Step 4: Four-quadrant decision ----
        try:
            if remote_changed and local_changed:
                # Conflict: remote wins, backup local first.
                backup_path = backup_local(spec, name)
                pull_incremental(client, username, name, spec, remote_files, local_resources)
                logger.warning(
                    "Conflict: remote and local both changed. "
                    "Remote wins. Local backup: %s", backup_path,
                )
            elif remote_changed:
                backup_path = backup_local(spec, name)
                pull_incremental(client, username, name, spec, remote_files, local_resources)
                logger.info("Pulled remote changes (backup: %s).", backup_path)
            elif local_changed:
                push_resources(client, username, name, framework, local_resources)
                logger.info("Pushed local changes.")
            else:
                # No changes on either side — skip baseline update.
                pass
        except Exception as exc:
            # Operation failed: do NOT update baseline; retry next cycle.
            logger.error("Sync failed (will retry): %s", exc)
            # Fall through to pipeline check, but skip baseline update.
            remote_changed = False
            local_changed = False

        # ---- Step 5: Update baseline (only on success) ----
        if remote_changed or local_changed:
            fresh = None
            for _attempt in range(3):
                try:
                    fresh = client.list_repo_files_detail(username, name)
                    break
                except ApiError as e:
                    if e.status == 500 and _attempt < 2:
                        time.sleep(3)
                        continue
                    logger.error("Failed to refresh baseline: %s", e)
                    break
                except Exception as exc:
                    logger.error("Failed to refresh baseline: %s", exc)
                    break
            if fresh is not None:
                fresh_max = max((f.committed_date for f in fresh), default=0)
                fresh_sha = {f.path: f.sha256 for f in fresh}
                state["last_commit_date"] = fresh_max
                state["remote_files"] = fresh_sha
            else:
                fresh_max = state["last_commit_date"]
                fresh_sha = state["remote_files"]

            save_sync_state(name, fresh_max, fresh_sha)

        # ---- Optional: local pipeline ----
        if local_ultron and not sessions_dirty:
            try:
                sessions_path = Path(sessions_dir)
                if sessions_path.is_dir():
                    current_mtime = max(
                        (f.stat().st_mtime for f in sessions_path.rglob('*.jsonl') if f.is_file()),
                        default=0.0,
                    )
                    if current_mtime > last_sessions_mtime:
                        sessions_dirty = True
            except Exception:
                pass

        cycle_counter += 1
        if local_ultron and sessions_dirty and cycle_counter % pipeline_every_n_cycles == 0:
            try:
                from ultron.services.background import run_pipeline_cycle
                local_ultron.ingestion_service.ingest(
                    [sessions_dir], agent_id=name
                )
                result = run_pipeline_cycle(local_ultron)
                if any(v for v in result.values() if isinstance(v, int) and v > 0):
                    logger.info("Pipeline cycle result: %s", result)
                    last_sessions_mtime = time.time()
                else:
                    sessions_dirty = False
                    last_sessions_mtime = time.time()
            except Exception as exc:
                logger.warning("Pipeline cycle failed: %s", exc)
                sessions_dirty = False

    logger.info("Watch stopped (signal received).")
    # Cleanup PID file.
    pf = pid_file()
    if pf.exists():
        pf.unlink(missing_ok=True)


def daemonize(target, *args, **kwargs):
    """Double-fork to daemonize *target* on Unix.

    Writes the child PID to the pid file so ``ultron stop`` can find it.
    """
    pf = pid_file()

    # First fork.
    pid = os.fork()
    if pid > 0:
        # Parent writes child PID after second fork.
        return

    # Decouple from parent.
    os.setsid()

    # Second fork.
    pid = os.fork()
    if pid > 0:
        # First child writes grandchild PID and exits.
        pf.write_text(str(pid), encoding="utf-8")
        os._exit(0)

    # Grandchild: redirect stdio.
    sys.stdout.flush()
    sys.stderr.flush()
    devnull = open(os.devnull, "r")
    log = open(str(log_file()), "a")
    os.dup2(devnull.fileno(), sys.stdin.fileno())
    os.dup2(log.fileno(), sys.stdout.fileno())
    os.dup2(log.fileno(), sys.stderr.fileno())

    # Write own PID (the actual daemon).
    pf.write_text(str(os.getpid()), encoding="utf-8")

    try:
        target(*args, **kwargs)
    finally:
        pf.unlink(missing_ok=True)
        os._exit(0)


def stop_daemon() -> bool:
    """Stop a running watch daemon by sending SIGTERM.

    Returns True if a process was stopped, False if none was running.
    """
    pf = pid_file()
    if not pf.exists():
        return False
    try:
        pid = int(pf.read_text().strip())
    except (ValueError, OSError):
        pf.unlink(missing_ok=True)
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    pf.unlink(missing_ok=True)
    return True
