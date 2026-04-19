# Copyright (c) ModelScope Contributors. All rights reserved.
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from ultron.core.models import MemoryRecord
from ultron.services.memory.conversation_extractor import ConversationExtractor


def _make_record(mid="id1") -> MemoryRecord:
    now = datetime.now()
    return MemoryRecord(
        id=mid, memory_type="pattern", content="c", context="",
        resolution="", tier="warm", hit_count=1, status="active",
        created_at=now, last_hit_at=now,
    )


class TestConversationExtractorUpload(unittest.TestCase):
    def test_upload_extracted_memories_skips_empty(self):
        mem_svc = MagicMock()
        now = datetime.now()
        rec = MemoryRecord(
            id="id1",
            memory_type="pattern",
            content="c",
            context="",
            resolution="",
            tier="warm",
            hit_count=1,
            status="active",
            created_at=now,
            last_hit_at=now,
        )
        mem_svc.upload_memory.return_value = rec

        ex = ConversationExtractor(memory_service=mem_svc, llm_orchestrator=None, database=None)
        out = ex._upload_extracted_memories([
            {"content": "", "context": "", "resolution": ""},
            {"content": "ok", "context": "", "resolution": "", "tags": ["t"]},
        ])
        self.assertEqual(len(out), 1)
        mem_svc.upload_memory.assert_called_once()


class TestConversationExtractorParseLines(unittest.TestCase):
    def _ex(self):
        return ConversationExtractor(memory_service=None, llm_orchestrator=None, database=None)

    def test_parse_valid_user_assistant(self):
        lines = [
            json.dumps({"role": "user", "content": "hello"}),
            json.dumps({"role": "assistant", "content": "hi"}),
        ]
        msgs = self._ex()._parse_lines_to_messages(lines)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["role"], "user")

    def test_parse_skips_metadata_type(self):
        lines = [
            json.dumps({"_type": "metadata", "role": "user", "content": "x"}),
            json.dumps({"role": "user", "content": "real"}),
        ]
        msgs = self._ex()._parse_lines_to_messages(lines)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["content"], "real")

    def test_parse_skips_empty_content(self):
        lines = [
            json.dumps({"role": "user", "content": ""}),
            json.dumps({"role": "assistant", "content": "ok"}),
        ]
        msgs = self._ex()._parse_lines_to_messages(lines)
        self.assertEqual(len(msgs), 1)

    def test_parse_skips_invalid_json(self):
        lines = ["not json", json.dumps({"role": "user", "content": "valid"})]
        msgs = self._ex()._parse_lines_to_messages(lines)
        self.assertEqual(len(msgs), 1)

    def test_parse_skips_unknown_roles(self):
        lines = [json.dumps({"role": "system", "content": "sys msg"})]
        msgs = self._ex()._parse_lines_to_messages(lines)
        self.assertEqual(len(msgs), 0)


class TestConversationExtractorSessionFile(unittest.TestCase):
    def _write_jsonl(self, path: Path, messages: list) -> None:
        path.write_text("\n".join(json.dumps(m) for m in messages), encoding="utf-8")

    def test_extract_file_not_found(self):
        ex = ConversationExtractor(memory_service=None, llm_orchestrator=None, database=None)
        result = ex.extract_from_session_file("/nonexistent/path.jsonl")
        self.assertFalse(result["success"])
        self.assertIn("Cannot read", result["error"])

    def test_extract_no_llm_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "session.jsonl"
            self._write_jsonl(f, [{"role": "user", "content": "hello"}])
            mem_svc = MagicMock()
            llm_orch = MagicMock()
            llm_orch.llm.is_available = False
            ex = ConversationExtractor(memory_service=mem_svc, llm_orchestrator=llm_orch, database=None)
            result = ex.extract_from_session_file(str(f))
            self.assertFalse(result["success"])
            self.assertIn("LLM unavailable", result["error"])

    def test_extract_already_processed_returns_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "session.jsonl"
            self._write_jsonl(f, [{"role": "user", "content": "hello"}])
            db = MagicMock()
            db.get_session_extract_progress.return_value = 999  # already past end
            ex = ConversationExtractor(memory_service=None, llm_orchestrator=None, database=db)
            result = ex.extract_from_session_file(str(f))
            self.assertTrue(result["success"])
            self.assertEqual(result["new_lines"], 0)

    def test_extract_empty_file_returns_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "session.jsonl"
            f.write_text("", encoding="utf-8")
            ex = ConversationExtractor(memory_service=None, llm_orchestrator=None, database=None)
            result = ex.extract_from_session_file(str(f))
            self.assertTrue(result["success"])


class TestConversationExtractorSessionPath(unittest.TestCase):
    def test_invalid_path_returns_error(self):
        ex = ConversationExtractor(memory_service=None, llm_orchestrator=None, database=None)
        result = ex.extract_from_session_path("/nonexistent/path.txt")
        self.assertFalse(result["success"])

    def test_directory_no_jsonl_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            ex = ConversationExtractor(memory_service=None, llm_orchestrator=None, database=None)
            result = ex.extract_from_session_path(tmp)
            self.assertTrue(result["success"])
            self.assertEqual(result["files_processed"], 0)


if __name__ == "__main__":
    unittest.main()
