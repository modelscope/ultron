# Copyright (c) ModelScope Contributors. All rights reserved.
import json
import logging
import logging.handlers
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

    def test_set_trace_id_returns_value(self):
        tid = set_trace_id("xyz999")
        self.assertEqual(tid, "xyz999")

    def test_get_trace_id_default(self):
        # After setting a known value, get returns it
        set_trace_id("known")
        self.assertEqual(get_trace_id(), "known")

    def test_generated_trace_id_is_hex(self):
        tid = set_trace_id("")
        int(tid, 16)  # should not raise


class TestFormatters(unittest.TestCase):
    def _make_record(self, msg="hello", level=logging.INFO, **extras):
        logger = logging.getLogger("test.fmt")
        record = logger.makeRecord(
            name="test", level=level, fn="", lno=0,
            msg=msg, args=(), exc_info=None,
        )
        for k, v in extras.items():
            setattr(record, k, v)
        return record

    def test_json_formatter_includes_extras(self):
        fmt = JsonFormatter()
        record = self._make_record(method="GET")
        line = fmt.format(record)
        data = json.loads(line)
        self.assertEqual(data["msg"], "hello")
        self.assertEqual(data["method"], "GET")

    def test_json_formatter_required_fields(self):
        fmt = JsonFormatter()
        record = self._make_record()
        data = json.loads(fmt.format(record))
        self.assertIn("ts", data)
        self.assertIn("level", data)
        self.assertIn("trace", data)
        self.assertIn("logger", data)
        self.assertIn("msg", data)

    def test_json_formatter_all_known_extras(self):
        fmt = JsonFormatter()
        record = self._make_record(
            method="POST", path="/memory/upload", status=200,
            duration_ms=42, action="upload", memory_id="m1",
            query="q", count=5, detail="ok",
        )
        data = json.loads(fmt.format(record))
        self.assertEqual(data["action"], "upload")
        self.assertEqual(data["count"], 5)
        self.assertEqual(data["status"], 200)

    def test_json_formatter_omits_none_extras(self):
        fmt = JsonFormatter()
        record = self._make_record()
        data = json.loads(fmt.format(record))
        self.assertNotIn("method", data)
        self.assertNotIn("action", data)

    def test_console_formatter_has_trace(self):
        fmt = ConsoleFormatter()
        record = self._make_record()
        set_trace_id("tid9")
        s = fmt.format(record)
        self.assertIn("tid9", s)

    def test_console_formatter_has_level(self):
        fmt = ConsoleFormatter()
        record = self._make_record(level=logging.WARNING)
        s = fmt.format(record)
        self.assertIn("WARNING", s)

    def test_console_formatter_includes_extras(self):
        fmt = ConsoleFormatter()
        record = self._make_record(action="test_action", count=3)
        s = fmt.format(record)
        self.assertIn("action=test_action", s)
        self.assertIn("count=3", s)

    def test_json_formatter_exception_info(self):
        fmt = JsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        record = self._make_record()
        record.exc_info = exc_info
        data = json.loads(fmt.format(record))
        self.assertIn("exception", data)
        self.assertIn("ValueError", data["exception"])


class TestSetupLogging(unittest.TestCase):
    def tearDown(self):
        # Clean up ultron logger handlers after each test
        root = logging.getLogger("ultron")
        root.handlers.clear()

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

    def test_console_handler_added(self):
        root = setup_logging(log_to_file=False, log_to_console=True, level="INFO")
        self.assertTrue(any(
            isinstance(h, logging.StreamHandler) and not isinstance(h, logging.handlers.RotatingFileHandler)
            for h in root.handlers
        ))

    def test_log_level_set(self):
        root = setup_logging(log_to_file=False, log_to_console=False, level="DEBUG")
        self.assertEqual(root.level, logging.DEBUG)

    def test_log_level_warning(self):
        root = setup_logging(log_to_file=False, log_to_console=False, level="WARNING")
        self.assertEqual(root.level, logging.WARNING)

    def test_creates_log_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = str(Path(tmp) / "nested" / "logs")
            setup_logging(log_dir=log_dir, log_to_file=True, log_to_console=False)
            self.assertTrue(Path(log_dir).is_dir())
            root = logging.getLogger("ultron")
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

    def test_log_event_default_level_info(self):
        root = logging.getLogger("ultron")
        root.setLevel(logging.DEBUG)
        buf = logging.handlers.BufferingHandler(10)
        root.addHandler(buf)
        try:
            log_event("info event")
            self.assertTrue(any(r.levelno == logging.INFO for r in buf.buffer))
        finally:
            root.removeHandler(buf)

    def test_log_event_warning_level(self):
        root = logging.getLogger("ultron")
        root.setLevel(logging.DEBUG)
        buf = logging.handlers.BufferingHandler(10)
        root.addHandler(buf)
        try:
            log_event("warn event", level="warning")
            self.assertTrue(any(r.levelno == logging.WARNING for r in buf.buffer))
        finally:
            root.removeHandler(buf)

    def test_log_event_message(self):
        root = logging.getLogger("ultron")
        root.setLevel(logging.INFO)
        buf = logging.handlers.BufferingHandler(10)
        root.addHandler(buf)
        try:
            log_event("my message")
            self.assertTrue(any(r.getMessage() == "my message" for r in buf.buffer))
        finally:
            root.removeHandler(buf)


if __name__ == "__main__":
    unittest.main()
