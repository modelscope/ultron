# Copyright (c) ModelScope Contributors. All rights reserved.
"""Tests for task_segments table, fingerprint, and segmentation logic."""
import json
import tempfile
import unittest
import uuid
from pathlib import Path

from ultron.core.database import Database


def _seg_quality_json(overall: float, task_type: str = "code") -> str:
    """Minimal quality_metrics blob: score and task_type live under summary."""
    return json.dumps({"summary": {"overall_score": overall, "task_type": task_type}})
from ultron.utils.token_budget import compute_segment_fingerprint


def _make_db(tmp: str) -> Database:
    return Database(str(Path(tmp) / "test_segments.db"))


class TestComputeSegmentFingerprint(unittest.TestCase):
    """compute_segment_fingerprint determinism and sensitivity tests."""

    def test_deterministic(self):
        msgs = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        fp1 = compute_segment_fingerprint(msgs)
        fp2 = compute_segment_fingerprint(msgs)
        self.assertEqual(fp1, fp2)
        self.assertEqual(len(fp1), 16)

    def test_different_content_different_fp(self):
        msgs_a = [{"role": "user", "content": "write code"}]
        msgs_b = [{"role": "user", "content": "debug code"}]
        self.assertNotEqual(
            compute_segment_fingerprint(msgs_a),
            compute_segment_fingerprint(msgs_b),
        )

    def test_content_change_changes_fp(self):
        """Simulates task C going from partial to complete."""
        partial = [
            {"role": "user", "content": "fix bug X"},
            {"role": "assistant", "content": "Looking into it..."},
        ]
        complete = partial + [
            {"role": "user", "content": "it's still broken"},
            {"role": "assistant", "content": "Found the root cause, here is the fix..."},
        ]
        fp_partial = compute_segment_fingerprint(partial)
        fp_complete = compute_segment_fingerprint(complete)
        self.assertNotEqual(fp_partial, fp_complete)

    def test_empty_messages(self):
        fp = compute_segment_fingerprint([])
        self.assertEqual(len(fp), 16)

    def test_role_matters(self):
        msgs_a = [{"role": "user", "content": "hello"}]
        msgs_b = [{"role": "assistant", "content": "hello"}]
        self.assertNotEqual(
            compute_segment_fingerprint(msgs_a),
            compute_segment_fingerprint(msgs_b),
        )


class TestTaskSegmentsDB(unittest.TestCase):
    """CRUD tests for the task_segments table."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = _make_db(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_and_get(self):
        sid = str(uuid.uuid4())
        inserted = self.db.save_task_segment(
            segment_id=sid,
            agent_id="agent1",
            session_file="/tmp/session.jsonl",
            segment_index=0,
            start_line=1,
            end_line=5,
            fingerprint="abc123",
            topic="write code",
        )
        self.assertTrue(inserted)

        segs = self.db.get_segments_for_session("agent1", "/tmp/session.jsonl")
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0]["id"], sid)
        self.assertEqual(segs[0]["fingerprint"], "abc123")
        self.assertEqual(segs[0]["topic"], "write code")
        self.assertEqual(segs[0]["labeled"], 0)

    def test_idempotent_by_fingerprint(self):
        """Same fingerprint = INSERT OR IGNORE → no duplicate."""
        for _ in range(3):
            self.db.save_task_segment(
                segment_id=str(uuid.uuid4()),
                agent_id="a",
                session_file="/f.jsonl",
                segment_index=0,
                start_line=1,
                end_line=5,
                fingerprint="samefp",
            )
        segs = self.db.get_segments_for_session("a", "/f.jsonl")
        self.assertEqual(len(segs), 1)

    def test_different_fingerprints_insert(self):
        for i, fp in enumerate(["fp1", "fp2", "fp3"]):
            self.db.save_task_segment(
                segment_id=str(uuid.uuid4()),
                agent_id="a",
                session_file="/f.jsonl",
                segment_index=i,
                start_line=i * 5 + 1,
                end_line=(i + 1) * 5,
                fingerprint=fp,
                topic=f"task {i}",
            )
        segs = self.db.get_segments_for_session("a", "/f.jsonl")
        self.assertEqual(len(segs), 3)

    def test_metric_labeling(self):
        sid = str(uuid.uuid4())
        self.db.save_task_segment(
            segment_id=sid, agent_id="a", session_file="/f.jsonl",
            segment_index=0, start_line=1, end_line=5, fingerprint="fp1",
        )
        # Initially unlabeled
        unlabeled = self.db.get_unlabeled_segments(10)
        self.assertEqual(len(unlabeled), 1)

        self.db.update_segment_metrics(sid, _seg_quality_json(0.8))

        unlabeled = self.db.get_unlabeled_segments(10)
        self.assertEqual(len(unlabeled), 0)

        eligible = self.db.get_memory_eligible_unextracted_segments(10)
        self.assertEqual(len(eligible), 1)
        self.assertEqual(eligible[0]["quality_score"], 0.8)

    def test_mark_memory_extracted(self):
        sid = str(uuid.uuid4())
        self.db.save_task_segment(
            segment_id=sid, agent_id="a", session_file="/f.jsonl",
            segment_index=0, start_line=1, end_line=5, fingerprint="fp1",
        )
        self.db.update_segment_metrics(sid, _seg_quality_json(0.7))

        eligible = self.db.get_memory_eligible_unextracted_segments(10)
        self.assertEqual(len(eligible), 1)

        self.db.mark_segment_memory_extracted(sid)

        eligible = self.db.get_memory_eligible_unextracted_segments(10)
        self.assertEqual(len(eligible), 0)

    def test_delete_segment(self):
        sid = str(uuid.uuid4())
        self.db.save_task_segment(
            segment_id=sid, agent_id="a", session_file="/f.jsonl",
            segment_index=0, start_line=1, end_line=5, fingerprint="fp1",
        )
        self.assertEqual(len(self.db.get_segments_for_session("a", "/f.jsonl")), 1)
        self.db.delete_segment(sid)
        self.assertEqual(len(self.db.get_segments_for_session("a", "/f.jsonl")), 0)

    def test_has_segments_for_session(self):
        self.assertFalse(self.db.has_segments_for_session("a", "/f.jsonl"))
        self.db.save_task_segment(
            segment_id=str(uuid.uuid4()), agent_id="a", session_file="/f.jsonl",
            segment_index=0, start_line=1, end_line=5, fingerprint="fp1",
        )
        self.assertTrue(self.db.has_segments_for_session("a", "/f.jsonl"))

    def test_get_segment_stats(self):
        for i in range(3):
            sid = str(uuid.uuid4())
            self.db.save_task_segment(
                segment_id=sid, agent_id="a", session_file="/f.jsonl",
                segment_index=i, start_line=i + 1, end_line=i + 5,
                fingerprint=f"fp{i}",
            )
            if i < 2:
                score = 0.85 if i == 0 else 0.5
                self.db.update_segment_metrics(sid, _seg_quality_json(score))

        stats = self.db.get_segment_stats()
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["labeled"], 2)
        self.assertEqual(stats["memory_eligible"], 1)
        self.assertEqual(stats["sft_eligible"], 1)
        self.assertEqual(stats["score_buckets"]["excellent"], 1)
        self.assertEqual(stats["score_buckets"]["weak"], 1)

    def test_get_segments_for_sft(self):
        sid = str(uuid.uuid4())
        self.db.save_task_segment(
            segment_id=sid, agent_id="a", session_file="/f.jsonl",
            segment_index=0, start_line=1, end_line=5, fingerprint="fp1",
        )
        self.db.update_segment_metrics(sid, _seg_quality_json(0.8))
        results = self.db.get_segments_for_sft(task_type="code", limit=10)
        self.assertEqual(len(results), 1)
        results_other = self.db.get_segments_for_sft(task_type="qa", limit=10)
        self.assertEqual(len(results_other), 0)

    def test_sft_training_record_schema_uses_eligible_count(self):
        with self.db._get_connection() as conn:
            cols = [row[1] for row in conn.execute("PRAGMA table_info(sft_training_records)")]
        self.assertIn("eligible_count_at_trigger", cols)
        self.assertNotIn("good" + "_count_at_trigger", cols)

        record_id = str(uuid.uuid4())
        self.db.save_sft_training_record(
            record_id=record_id,
            eligible_count=3,
            samples_exported=2,
            base_model="base",
        )
        with self.db._get_connection() as conn:
            row = conn.execute(
                "SELECT eligible_count_at_trigger FROM sft_training_records WHERE id=?",
                (record_id,),
            ).fetchone()
        self.assertEqual(row[0], 3)


class TestArchiveMemoriesByTag(unittest.TestCase):
    """Test the archive_memories_by_tag method in db_memory."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = _make_db(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_archive_by_segment_tag(self):
        import json
        from datetime import datetime
        from ultron.core.models import MemoryRecord

        now = datetime.now()
        seg_id = "abcd1234"
        tag = f"segment:{seg_id}"

        # Create a memory with the segment tag
        rec = MemoryRecord(
            id=str(uuid.uuid4()), memory_type="pattern",
            content="some knowledge", context="ctx", resolution="res",
            tier="warm", hit_count=1, status="active",
            created_at=now, last_hit_at=now,
            tags=["trajectory", tag],
        )
        self.db.save_memory_record(rec)

        # Create another memory without the tag
        rec2 = MemoryRecord(
            id=str(uuid.uuid4()), memory_type="pattern",
            content="other knowledge", context="ctx", resolution="res",
            tier="warm", hit_count=1, status="active",
            created_at=now, last_hit_at=now,
            tags=["trajectory", "segment:other123"],
        )
        self.db.save_memory_record(rec2)

        archived = self.db.archive_memories_by_tag(tag)
        self.assertEqual(archived, 1)

        # Verify the tagged memory is archived
        row = self.db.get_memory_record(rec.id)
        self.assertEqual(row["status"], "archived")

        # Verify the other memory is still active
        row2 = self.db.get_memory_record(rec2.id)
        self.assertEqual(row2["status"], "active")


if __name__ == "__main__":
    unittest.main()
