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

from .cache import log_file, pid_file
from .sync import _md5, zip_resources

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


def _snapshot(resources: Dict[str, str]) -> Dict[str, str]:
    """Build a snapshot of ``{rel_path: md5}`` from collected resources."""
    return {rel: _md5(content) for rel, content in resources.items()}


def watch_loop(spec, client, username: str, name: str, framework: str, interval: int = 3, sessions_dir: str = None):
    """Poll for file changes and upload when detected.

    Runs indefinitely until SIGTERM is received.
    If *sessions_dir* is provided and a valid LLM API key is configured, also runs the
    local memory/skill extraction pipeline periodically.
    """
    logger = _get_logger()
    root: Path = spec.workspace_root
    logger.info("Watch started for %s/%s (root=%s, interval=%ds)", username, name, root, interval)

    # Initial snapshot.
    resources = spec.collect()
    prev_snap = _snapshot(resources)

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
    # Run pipeline every N poll cycles (100 * 3s = ~5 min by default)
    pipeline_every_n_cycles = 100
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
        current_resources = spec.collect()
        curr_snap = _snapshot(current_resources)

        if curr_snap != prev_snap:
            changed = set(curr_snap.keys()) ^ set(prev_snap.keys())
            for k in set(curr_snap.keys()) & set(prev_snap.keys()):
                if curr_snap[k] != prev_snap[k]:
                    changed.add(k)
            logger.info("Detected changes in: %s", ", ".join(sorted(changed)))
            try:
                zip_bytes = zip_resources(current_resources)
                file_id = client.upload_file(zip_bytes)
                client.create_repo(
                    username, name, framework,
                    system_prompt_files=file_id,
                )
                logger.info("Upload complete (%d bytes zip).", len(zip_bytes))
            except Exception as exc:
                logger.error("Upload failed: %s", exc)
            prev_snap = curr_snap

        # Check if sessions directory has new/modified files
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

        # Periodically run local pipeline for memory/skill extraction
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
                    sessions_dirty = False  # no new work, pause until sessions change
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
