# Copyright (c) ModelScope Contributors. All rights reserved.
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from ultron.config import UltronConfig
from ultron.services.ingestion import IngestionService


class TestIngestionExpand(unittest.TestCase):
    def test_expand_paths_skips_hidden(self):
        with tempfile.TemporaryDirectory() as root:
            r = Path(root)
            (r / "vis.jsonl").write_text('{"role":"user","content":"x"}\n', encoding="utf-8")
            hid = r / ".hidden"
            hid.mkdir()
            (hid / "a.jsonl").write_text('{"role":"user","content":"y"}\n', encoding="utf-8")
            out = IngestionService._expand_paths([str(r)])
            self.assertEqual(len(out), 1)
            self.assertTrue(out[0].endswith("vis.jsonl"))

    def test_ingest_empty_paths(self):
        svc = IngestionService(MagicMock(), MagicMock(), config=UltronConfig())
        res = svc.ingest([], agent_id="")
        self.assertEqual(res["total_files"], 0)
        self.assertEqual(res["successful"], 0)

    def test_error_result_shape(self):
        d = IngestionService._error_result("bad", file_path="/x")
        self.assertFalse(d["success"])
        self.assertEqual(d["error"], "bad")
        self.assertEqual(d["file_path"], "/x")

    def test_ingest_text_no_llm(self):
        llm = MagicMock()
        llm.is_available = False
        svc = IngestionService(MagicMock(), llm, config=UltronConfig())
        res = svc.ingest_text("hello")
        self.assertFalse(res["success"])
        self.assertIn("unavailable", res["error"].lower())

    def test_expand_paths_nonexistent_skipped(self):
        out = IngestionService._expand_paths(["/nonexistent/path/file.txt"])
        self.assertEqual(out, [])

    def test_expand_paths_single_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "a.jsonl"
            f.write_text('{"role":"user","content":"hello"}\n', encoding="utf-8")
            out = IngestionService._expand_paths([str(f)])
            self.assertEqual(len(out), 1)

    def test_expand_paths_nested_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            (r / "sub").mkdir()
            (r / "sub" / "b.jsonl").write_text('{"role":"user","content":"x"}\n', encoding="utf-8")
            (r / "a.jsonl").write_text('{"role":"user","content":"y"}\n', encoding="utf-8")
            out = IngestionService._expand_paths([str(r)])
            self.assertEqual(len(out), 2)


class TestIngestionText(unittest.TestCase):
    def test_ingest_text_empty_string(self):
        llm = MagicMock()
        llm.is_available = True
        svc = IngestionService(MagicMock(), llm, config=UltronConfig())
        res = svc.ingest_text("   ")
        self.assertFalse(res["success"])
        self.assertIn("Empty", res["error"])

    def test_ingest_text_no_memories_extracted(self):
        llm = MagicMock()
        llm.is_available = True
        orch = MagicMock()
        orch.extract_memories_from_text.return_value = []
        svc = IngestionService(MagicMock(), llm, config=UltronConfig(), llm_orchestrator=orch)
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
        svc = IngestionService(mem, llm, config=UltronConfig(), llm_orchestrator=orch)
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
        svc = IngestionService(mem, llm, config=UltronConfig(), llm_orchestrator=orch)
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
        svc = IngestionService(mem, llm, config=UltronConfig(), llm_orchestrator=orch)
        svc.ingest_text("content", source_file="/tmp/notes.txt")
        call_kwargs = mem.upload_memory.call_args
        self.assertIn("source:notes.txt", call_kwargs[1]["tags"])


class TestIngestionFile(unittest.TestCase):
    def test_ingest_skips_non_jsonl_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "notes.txt"
            f.write_text("some notes", encoding="utf-8")
            svc = IngestionService(MagicMock(), MagicMock(), config=UltronConfig())
            res = svc.ingest([str(f)])
            self.assertEqual(res["total_files"], 0)
            self.assertEqual(res["successful"], 0)

    def test_ingest_jsonl_records_trajectories(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "session.jsonl"
            f.write_text(
                '{"role":"user","content":"hi"}\n{"role":"assistant","content":"there"}\n',
                encoding="utf-8",
            )
            traj = MagicMock()
            traj.db.get_session_row.return_value = None  # no existing session row
            db = MagicMock()
            svc = IngestionService(
                MagicMock(),
                MagicMock(),
                config=UltronConfig(),
                database=db,
                trajectory_service=traj,
            )
            res = svc.ingest([str(f)], agent_id="a1")
            self.assertEqual(res["total_files"], 1)
            self.assertTrue(res["results"][0]["success"])
            traj.record_session.assert_called_once()
            db.update_session_extract_progress.assert_called_once()

    def test_ingest_jsonl_without_trajectory_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "session.jsonl"
            f.write_text('{"role":"user","content":"hi"}\n', encoding="utf-8")
            svc = IngestionService(MagicMock(), MagicMock(), config=UltronConfig())
            res = svc.ingest([str(f)])
            self.assertFalse(res["results"][0]["success"])
            self.assertIn(
                "trajectory",
                (res["results"][0].get("error") or "").lower(),
            )


if __name__ == "__main__":
    unittest.main()
