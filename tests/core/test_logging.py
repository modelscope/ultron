# Copyright (c) ModelScope Contributors. All rights reserved.
import json
import logging
import tempfile
import unittest
from pathlib import Path

from ultron.core.logging import (
    ConsoleFormatter,
    JsonFormatter,
    get_trace_id,
    log_event,
    set_trace_id,
    setup_logging,
)


class TestTraceContext(unittest.TestCase):
    def test_set_get_trace_id(self):
        tid = set_trace_id("abc123")
        self.assertEqual(tid, "abc123")
        self.assertEqual(get_trace_id(), "abc123")

    def test_set_trace_id_generates(self):
        t1 = set_trace_id("")
        self.assertEqual(len(t1), 12)


class TestFormatters(unittest.TestCase):
    def test_json_formatter_includes_extras(self):
        fmt = JsonFormatter()
        logger = logging.getLogger("test.json")
        record = logger.makeRecord(
            name="test",
            level=logging.INFO,
            fn="",
            lno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )
        record.method = "GET"
        line = fmt.format(record)
        data = json.loads(line)
        self.assertEqual(data["msg"], "hello")
        self.assertEqual(data["method"], "GET")

    def test_console_formatter_has_trace(self):
        fmt = ConsoleFormatter()
        logger = logging.getLogger("test.console")
        record = logger.makeRecord(
            name="test",
            level=logging.INFO,
            fn="",
            lno=0,
            msg="x",
            args=(),
            exc_info=None,
        )
        set_trace_id("tid9")
        s = fmt.format(record)
        self.assertIn("tid9", s)


class TestSetupLogging(unittest.TestCase):
    def test_file_and_console_disabled(self):
        root = setup_logging(log_to_file=False, log_to_console=False, level="ERROR")
        self.assertEqual(len(root.handlers), 0)

    def test_json_file_handler(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = str(Path(tmp) / "logs")
            root = setup_logging(
                log_dir=log_dir,
                level="INFO",
                log_to_file=True,
                log_to_console=False,
            )
            self.assertTrue(any(
                isinstance(h, logging.handlers.RotatingFileHandler)
                for h in root.handlers
            ))
            for h in root.handlers:
                root.removeHandler(h)


class TestLogEvent(unittest.TestCase):
    def test_log_event_with_extra(self):
        root = logging.getLogger("ultron")
        root.setLevel(logging.INFO)
        buf = logging.handlers.BufferingHandler(10)
        root.addHandler(buf)
        try:
            log_event("evt", action="test_action", count=2)
            self.assertTrue(any(
                getattr(r, "action", None) == "test_action"
                for r in buf.buffer
            ))
        finally:
            root.removeHandler(buf)


if __name__ == "__main__":
    unittest.main()
