# Copyright (c) ModelScope Contributors. All rights reserved.
"""quality_score [0, 1] contract for task_segments (memory vs SFT coarse filters)."""
import json
import tempfile
import unittest
import uuid
from pathlib import Path

from ultron.core.database import Database


def _seg_quality_json(overall: float, task_type: str = "code") -> str:
    return json.dumps({"summary": {"overall_score": overall, "task_type": task_type}})


def _db(tmp: str) -> Database:
    return Database(str(Path(tmp) / "score_contract.db"))


class TestTaskSegmentScoreContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = _db(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _new_seg(self) -> str:
        sid = str(uuid.uuid4())
        self.db.save_task_segment(
            segment_id=sid,
            agent_id="a",
            session_file="/f.jsonl",
            segment_index=0,
            start_line=1,
            end_line=2,
            fingerprint=str(uuid.uuid4())[:12],
        )
        return sid

    def test_memory_coarse_069_vs_07(self):
        s69 = self._new_seg()
        s70 = self._new_seg()
        self.db.update_segment_metrics(s69, _seg_quality_json(0.69))
        self.db.update_segment_metrics(s70, _seg_quality_json(0.7))
        m70 = self.db.get_memory_eligible_unextracted_segments(10, min_quality_score=0.7)
        self.assertEqual({r["id"] for r in m70}, {s70})
        self.assertNotIn(s69, {r["id"] for r in m70})

    def test_sft_coarse_079_vs_08(self):
        s79 = self._new_seg()
        s80 = self._new_seg()
        self.db.update_segment_metrics(s79, _seg_quality_json(0.79))
        self.db.update_segment_metrics(s80, _seg_quality_json(0.8))
        sft = self.db.get_segments_for_sft(
            task_type="code", limit=10, min_quality_score=0.8,
        )
        self.assertEqual({r["id"] for r in sft}, {s80})


if __name__ == "__main__":
    unittest.main()
