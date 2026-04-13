# Copyright (c) ModelScope Contributors. All rights reserved.
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from ultron.config import UltronConfig
from ultron.services.smart_ingestion import SmartIngestionService


class TestSmartIngestionExpand(unittest.TestCase):
    def test_expand_paths_skips_hidden(self):
        with tempfile.TemporaryDirectory() as root:
            r = Path(root)
            (r / "vis.txt").write_text("x", encoding="utf-8")
            hid = r / ".hidden"
            hid.mkdir()
            (hid / "a.txt").write_text("y", encoding="utf-8")
            out = SmartIngestionService._expand_paths([str(r)])
            self.assertEqual(len(out), 1)
            self.assertTrue(out[0].endswith("vis.txt"))

    def test_ingest_empty_paths(self):
        mem = MagicMock()
        llm = MagicMock()
        svc = SmartIngestionService(mem, llm, config=UltronConfig())
        res = svc.ingest([], agent_id="")
        self.assertEqual(res["total_files"], 0)
        self.assertEqual(res["successful"], 0)

    def test_error_result_shape(self):
        d = SmartIngestionService._error_result("bad", file_path="/x")
        self.assertFalse(d["success"])
        self.assertEqual(d["error"], "bad")
        self.assertEqual(d["file_path"], "/x")

    def test_ingest_text_no_llm(self):
        mem = MagicMock()
        llm = MagicMock()
        llm.is_available = False
        svc = SmartIngestionService(mem, llm, config=UltronConfig())
        res = svc.ingest_text("hello")
        self.assertFalse(res["success"])
        self.assertIn("unavailable", res["error"].lower())


if __name__ == "__main__":
    unittest.main()
