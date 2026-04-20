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
        svc = SmartIngestionService(MagicMock(), MagicMock(), config=UltronConfig())
        res = svc.ingest([], agent_id="")
        self.assertEqual(res["total_files"], 0)
        self.assertEqual(res["successful"], 0)

    def test_error_result_shape(self):
        d = SmartIngestionService._error_result("bad", file_path="/x")
        self.assertFalse(d["success"])
        self.assertEqual(d["error"], "bad")
        self.assertEqual(d["file_path"], "/x")

    def test_ingest_text_no_llm(self):
        llm = MagicMock()
        llm.is_available = False
        svc = SmartIngestionService(MagicMock(), llm, config=UltronConfig())
        res = svc.ingest_text("hello")
        self.assertFalse(res["success"])
        self.assertIn("unavailable", res["error"].lower())

    def test_expand_paths_nonexistent_skipped(self):
        out = SmartIngestionService._expand_paths(["/nonexistent/path/file.txt"])
        self.assertEqual(out, [])

    def test_expand_paths_single_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "a.txt"
            f.write_text("hello", encoding="utf-8")
            out = SmartIngestionService._expand_paths([str(f)])
            self.assertEqual(len(out), 1)

    def test_expand_paths_nested_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            (r / "sub").mkdir()
            (r / "sub" / "b.txt").write_text("x", encoding="utf-8")
            (r / "a.txt").write_text("y", encoding="utf-8")
            out = SmartIngestionService._expand_paths([str(r)])
            self.assertEqual(len(out), 2)


class TestSmartIngestionText(unittest.TestCase):
    def test_ingest_text_empty_string(self):
        llm = MagicMock()
        llm.is_available = True
        svc = SmartIngestionService(MagicMock(), llm, config=UltronConfig())
        res = svc.ingest_text("   ")
        self.assertFalse(res["success"])
        self.assertIn("Empty", res["error"])

    def test_ingest_text_no_memories_extracted(self):
        llm = MagicMock()
        llm.is_available = True
        orch = MagicMock()
        orch.extract_memories_from_text.return_value = []
        svc = SmartIngestionService(MagicMock(), llm, config=UltronConfig(), llm_orchestrator=orch)
        res = svc.ingest_text("some content here")
        self.assertFalse(res["success"])
        self.assertEqual(res["memories_extracted"], 0)

    def test_ingest_text_uploads_memories(self):
        mem = MagicMock()
        record = MagicMock()
        record.to_dict.return_value = {"id": "x", "content": "c"}
        mem.upload_memory.return_value = record
        llm = MagicMock()
        llm.is_available = True
        orch = MagicMock()
        orch.extract_memories_from_text.return_value = [
            {"content": "memory 1", "tags": ["t1"]},
            {"content": "memory 2", "tags": []},
        ]
        svc = SmartIngestionService(mem, llm, config=UltronConfig(), llm_orchestrator=orch)
        res = svc.ingest_text("some content")
        self.assertTrue(res["success"])
        self.assertEqual(res["memories_uploaded"], 2)

    def test_ingest_text_skips_empty_content_memories(self):
        mem = MagicMock()
        record = MagicMock()
        record.to_dict.return_value = {"id": "x"}
        mem.upload_memory.return_value = record
        llm = MagicMock()
        llm.is_available = True
        orch = MagicMock()
        orch.extract_memories_from_text.return_value = [
            {"content": "", "tags": []},
            {"content": "valid memory", "tags": []},
        ]
        svc = SmartIngestionService(mem, llm, config=UltronConfig(), llm_orchestrator=orch)
        res = svc.ingest_text("content")
        self.assertEqual(res["memories_uploaded"], 1)

    def test_ingest_text_with_source_file_tag(self):
        mem = MagicMock()
        record = MagicMock()
        record.to_dict.return_value = {"id": "x"}
        mem.upload_memory.return_value = record
        llm = MagicMock()
        llm.is_available = True
        orch = MagicMock()
        orch.extract_memories_from_text.return_value = [{"content": "note", "tags": []}]
        svc = SmartIngestionService(mem, llm, config=UltronConfig(), llm_orchestrator=orch)
        svc.ingest_text("content", source_file="/tmp/notes.txt")
        call_kwargs = mem.upload_memory.call_args
        self.assertIn("source:notes.txt", call_kwargs[1]["tags"])


class TestSmartIngestionFile(unittest.TestCase):
    def test_ingest_single_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "notes.txt"
            f.write_text("some notes", encoding="utf-8")
            mem = MagicMock()
            record = MagicMock()
            record.to_dict.return_value = {"id": "x"}
            mem.upload_memory.return_value = record
            llm = MagicMock()
            llm.is_available = True
            orch = MagicMock()
            orch.extract_memories_from_text.return_value = [{"content": "note", "tags": []}]
            svc = SmartIngestionService(mem, llm, config=UltronConfig(), llm_orchestrator=orch)
            res = svc.ingest([str(f)])
            self.assertEqual(res["total_files"], 1)
            self.assertEqual(res["successful"], 1)

    def test_ingest_jsonl_delegates_to_extractor(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "session.jsonl"
            f.write_text('{"role":"user","content":"hi"}\n', encoding="utf-8")
            extractor = MagicMock()
            extractor.extract_from_session_file.return_value = {
                "success": True, "memories_uploaded": 1, "total_uploaded": 1,
            }
            svc = SmartIngestionService(
                MagicMock(), MagicMock(), config=UltronConfig(),
                conversation_extractor=extractor,
            )
            res = svc.ingest([str(f)])
            extractor.extract_from_session_file.assert_called_once()
            self.assertEqual(res["total_files"], 1)

    def test_ingest_jsonl_no_extractor_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "session.jsonl"
            f.write_text('{"role":"user","content":"hi"}\n', encoding="utf-8")
            svc = SmartIngestionService(MagicMock(), MagicMock(), config=UltronConfig())
            res = svc.ingest([str(f)])
            self.assertFalse(res["results"][0]["success"])


if __name__ == "__main__":
    unittest.main()
