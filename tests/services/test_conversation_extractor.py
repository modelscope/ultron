# Copyright (c) ModelScope Contributors. All rights reserved.
import unittest
from datetime import datetime
from unittest.mock import MagicMock

from ultron.core.models import MemoryRecord
from ultron.services.memory.conversation_extractor import ConversationExtractor


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


if __name__ == "__main__":
    unittest.main()
