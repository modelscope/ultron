# Copyright (c) ModelScope Contributors. All rights reserved.
import json
import logging
import logging.handlers
import os
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

# Per-request id propagated through handlers (HTTP, memory pipeline, etc.)
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")


def get_trace_id() -> str:
    """Return the trace id for the current context."""
    return trace_id_var.get()


def set_trace_id(tid: str = "") -> str:
    """Assign a trace id (or generate one) and return it."""
    tid = tid or uuid.uuid4().hex[:12]
    trace_id_var.set(tid)
    return tid


class JsonFormatter(logging.Formatter):
    """
    JSON lines for the rotating file handler under ~/.ultron/logs.
    """

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "trace": get_trace_id(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in (
            "method", "path", "status", "duration_ms",
            "action", "memory_id", "query", "count",
            "detail",
        ):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """
    Short colored one-line format for stderr.
    """

    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        tid = get_trace_id()
        ts = datetime.now().strftime("%H:%M:%S")

        extras = []
        for key in ("method", "path", "status", "duration_ms",
                    "action", "count"):
            val = getattr(record, key, None)
            if val is not None:
                extras.append(f"{key}={val}")
        extra_str = f" [{', '.join(extras)}]" if extras else ""

        return (
            f"{ts} {color}{record.levelname:>5}{self.RESET} "
            f"[{tid}] {record.name}: {record.getMessage()}{extra_str}"
        )


def setup_logging(
    log_dir: str = "",
    level: str = "INFO",
    log_to_file: bool = True,
    log_to_console: bool = True,
) -> logging.Logger:
    """
    Attach console and/or rotating-file handlers to the ``ultron`` logger tree.

    Args:
        log_dir: Directory for ultron.log (default ~/.ultron/logs).
        level: Root level name, e.g. INFO.
        log_to_file: Enable JSON file output.
        log_to_console: Enable colored stderr output.
    """
    root = logging.getLogger("ultron")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    if log_to_console:
        ch = logging.StreamHandler(sys.stderr)
        ch.setFormatter(ConsoleFormatter())
        root.addHandler(ch)

    if log_to_file:
        if not log_dir:
            log_dir = os.path.join(os.path.expanduser("~/.ultron"), "logs")
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        log_file = os.path.join(log_dir, "ultron.log")

        fh = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5,
            encoding="utf-8",
        )
        fh.setFormatter(JsonFormatter())
        root.addHandler(fh)

    for name in ("uvicorn", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = root.handlers
        uv_logger.setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)

    return root


logger = logging.getLogger("ultron")


def log_event(
    msg: str,
    level: str = "info",
    **kwargs,
) -> None:
    """
    Emit a log record with arbitrary extra attributes (mirrored into JsonFormatter).

    Example:
        log_event("upload done", action="upload_memory", memory_id="...")
    """
    lvl = getattr(logging, level.upper(), logging.INFO)
    record = logger.makeRecord(
        name="ultron",
        level=lvl,
        fn="",
        lno=0,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for key, val in kwargs.items():
        setattr(record, key, val)
    logger.handle(record)
