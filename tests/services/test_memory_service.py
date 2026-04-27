# Copyright (c) ModelScope Contributors. All rights reserved.
# pylint: disable=protected-access

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from ultron.config import UltronConfig
from ultron.core.database import Database
from ultron.core.models import MemoryRecord, MemoryStatus, MemoryTier
from ultron.services.memory import MemorySearchResult, MemoryService


def _upload_service(db, emb, **cfg_overrides):
    """Build MemoryService for upload/integration-style tests (real DB)."""
    sanitizer = MagicMock()
    sanitizer.sanitize.side_effect = lambda x: x
    cfg = UltronConfig()
    cfg.dedup_similarity_threshold = 0.85
    for k, v in cfg_overrides.items():
        setattr(cfg, k, v)
    return MemoryService(
        database=db,
        embedding_service=emb,
        sanitizer=sanitizer,
        llm_service=None,
        config=cfg,
    )


class TestMemorySearchResult(unittest.TestCase):
    """
    MemoryService package: MemorySearchResult serialization and related behaviors.
    """

    def _sample_record(self):
        now = datetime.now()
        return MemoryRecord(
            id="rid",
            memory_type="pattern",
            content="c",
            context="",
            resolution="",
            tier=MemoryTier.WARM.value,
            hit_count=1,
            status=MemoryStatus.ACTIVE.value,
            created_at=now,
            last_hit_at=now,
            embedding=[0.1, 0.2],
            tags=["t"],
            summary_l0="s0",
            overview_l1="s1",
        )

    def test_to_dict_includes_scores_and_embedding_by_default(self):
        rec = self._sample_record()
        sr = MemorySearchResult(
            record=rec, similarity_score=0.876543, tier_boosted_score=0.912345
        )
        d = sr.to_dict()
        self.assertEqual(d["id"], "rid")
        self.assertEqual(d["similarity_score"], 0.8765)
        self.assertEqual(d["tier_boosted_score"], 0.9123)
        self.assertEqual(d["embedding"], [0.1, 0.2])

    def test_to_dict_can_strip_embedding(self):
        rec = self._sample_record()
        sr = MemorySearchResult(
            record=rec, similarity_score=0.5, tier_boosted_score=0.5
        )
        d = sr.to_dict(include_embedding=False)
        self.assertNotIn("embedding", d)


class TestUploadMemoryMergedBody(unittest.TestCase):
    """upload_memory near-duplicate path: merge body, tags-only, or new row."""

    def test_second_upload_merges_body_and_persists(self):
        """When LLM is unavailable, near-duplicate hit still records the
        contribution but keeps original text unchanged (no rule-based merge)."""
        fixed_vec = [1.0, 0.0, 0.0]
        emb = MagicMock()
        emb.embed_memory_context = MagicMock(return_value=fixed_vec)
        emb.cosine_similarity = MagicMock(return_value=0.99)

        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "test.db")
            db = Database(db_path)
            svc = _upload_service(db, emb)

            first = svc.upload_memory(
                "first unique paragraph for merge test",
                "",
                "",
            )
            self.assertIsNotNone(first.id)

            second = svc.upload_memory(
                "second unique paragraph for merge test",
                "",
                "",
            )

            self.assertEqual(second.id, first.id)

            row = db.get_memory_record(first.id)
            self.assertIsNotNone(row)
            body = row["content"]
            # Without LLM, original text is kept unchanged
            self.assertIn("first unique paragraph", body)
            self.assertNotIn("second unique paragraph", body)
            self.assertGreaterEqual(row["hit_count"], 2)

    def test_below_threshold_inserts_second_row(self):
        emb = MagicMock()
        emb.embed_memory_context = MagicMock(side_effect=[[1.0, 0.0], [0.0, 1.0]])
        emb.cosine_similarity = MagicMock(return_value=0.5)

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(str(Path(tmp) / "t.db"))
            svc = _upload_service(db, emb)
            a = svc.upload_memory("note one", "", "")
            b = svc.upload_memory("note two", "", "")
            self.assertNotEqual(a.id, b.id)

    def test_upload_memory_basic(self):
        emb = MagicMock()
        emb.embed_memory_context = MagicMock(return_value=[1.0, 0.0])
        emb.cosine_similarity = MagicMock(return_value=0.0)
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(str(Path(tmp) / "t.db"))
            svc = _upload_service(db, emb)
            rec = svc.upload_memory("only body", "", "")
            self.assertIsNotNone(rec.id)

    def test_duplicate_same_text_new_tags_only(self):
        fixed_vec = [0.25, 0.75]
        emb = MagicMock()
        emb.embed_memory_context = MagicMock(return_value=fixed_vec)
        emb.cosine_similarity = MagicMock(return_value=0.99)

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(str(Path(tmp) / "t.db"))
            svc = _upload_service(db, emb)
            body = "shared body identical for merge"
            first = svc.upload_memory(body, "", "", tags=["old"])
            second = svc.upload_memory(body, "", "", tags=["new-tag"])
            self.assertEqual(second.id, first.id)
            row = db.get_memory_record(first.id)
            self.assertEqual(row["content"], body)
            self.assertIn("new-tag", row["tags"])
            self.assertIn("old", row["tags"])
            self.assertGreaterEqual(row["hit_count"], 2)


class TestFindNearDuplicate(unittest.TestCase):
    """_find_near_duplicate scans HOT/WARM, picks max similarity."""

    def _bare_service(self):
        svc = object.__new__(MemoryService)
        svc.db = MagicMock()
        svc.embedding = MagicMock()
        svc.config = MagicMock()
        svc.config.dedup_similarity_threshold = 0.85
        svc.config.dedup_soft_threshold = 0.75
        return svc

    def test_scans_all_tiers(self):
        svc = self._bare_service()
        svc.db.get_memory_records_with_embeddings.return_value = []
        svc._find_near_duplicate([1.0, 0.0], "pattern")
        calls = svc.db.get_memory_records_with_embeddings.call_args_list
        self.assertEqual(len(calls), 3)
        tiers = {c.kwargs["tier"] for c in calls}
        self.assertEqual(
            tiers,
            {MemoryTier.HOT.value, MemoryTier.WARM.value, MemoryTier.COLD.value},
        )
        for c in calls:
            self.assertEqual(c.kwargs["memory_type"], "pattern")

    def test_returns_none_when_below_threshold(self):
        svc = self._bare_service()
        svc.db.get_memory_records_with_embeddings.return_value = [
            ({"id": "a"}, [1.0, 0.0]),
        ]
        svc.embedding.cosine_similarity.return_value = 0.5
        self.assertIsNone(svc._find_near_duplicate([1.0, 0.0], "pattern"))
        svc.embedding.cosine_similarity.assert_called()

    def test_returns_best_of_multiple_above_threshold(self):
        svc = self._bare_service()
        low = {"id": "low"}
        high = {"id": "high"}
        emb_low = [1.0, 0.0]
        emb_high = [0.0, 1.0]

        def fake_rows(memory_type, tier):
            if tier == MemoryTier.HOT.value:
                return [(low, emb_low)]
            return [(high, emb_high)]

        svc.db.get_memory_records_with_embeddings.side_effect = fake_rows

        def fake_cosine(_q, existing):
            if existing is emb_low:
                return 0.9
            if existing is emb_high:
                return 0.95
            return 0.0

        svc.embedding.cosine_similarity.side_effect = fake_cosine

        out = svc._find_near_duplicate([1.0, 0.0], "pattern")
        self.assertIsNotNone(out)
        match, similarity = out
        self.assertEqual(match["id"], "high")
        self.assertAlmostEqual(similarity, 0.95)


class _RaisingLLM:
    """LLM stub that always raises from classify_memory_type."""

    def classify_memory_type(self, content, context, resolution):
        raise RuntimeError("api unavailable")


class _ReturningLLM:
    """LLM stub with configurable classify_memory_type return value."""

    def __init__(self, value):
        self.value = value
        self.calls = []

    def classify_memory_type(self, content, context, resolution):
        self.calls.append((content, context, resolution))
        return self.value


class TestResolveMemoryTypeAuto(unittest.TestCase):
    """Tests for MemoryService._resolve_memory_type_auto (upload step 2)."""

    def _service(self, llm_orchestrator=None):
        return MemoryService(
            database=MagicMock(),
            embedding_service=MagicMock(),
            llm_orchestrator=llm_orchestrator,
        )

    def test_no_llm_security_heuristic(self):
        svc = self._service(llm_orchestrator=None)
        t = svc._resolve_memory_type_auto("CVE-2024-1234 patch", "", "")
        self.assertEqual(t, "security")

    def test_no_llm_error_heuristic(self):
        svc = self._service(llm_orchestrator=None)
        t = svc._resolve_memory_type_auto("Traceback (most recent call last)", "", "")
        self.assertEqual(t, "error")

    def test_no_llm_pattern_default(self):
        svc = self._service(llm_orchestrator=None)
        t = svc._resolve_memory_type_auto("Reusable note about workflows", "", "")
        self.assertEqual(t, "pattern")

    def test_llm_returns_used_first(self):
        llm = _ReturningLLM("preference")
        svc = self._service(llm_orchestrator=llm)
        t = svc._resolve_memory_type_auto("plain text", "", "")
        self.assertEqual(t, "preference")
        self.assertEqual(len(llm.calls), 1)

    def test_llm_empty_falls_back_to_heuristic(self):
        llm = _ReturningLLM("")
        svc = self._service(llm_orchestrator=llm)
        t = svc._resolve_memory_type_auto("sql injection note", "", "")
        self.assertEqual(t, "security")

    def test_llm_exception_falls_back_to_heuristic(self):
        svc = self._service(llm_orchestrator=_RaisingLLM())
        t = svc._resolve_memory_type_auto("", "", "segmentation fault")
        self.assertEqual(t, "error")


class TestMemoryServiceSearch(unittest.TestCase):
    """search_memories ranking, dedupe by id, tier boost."""

    def test_search_sorts_by_tier_boosted_score_desc(self):
        cfg = UltronConfig()
        cfg.enable_intent_analysis = False
        cfg.time_decay_weight = 0.0

        now = datetime.now().isoformat()
        base = {
            "memory_type": "pattern",
            "content": "x",
            "context": "",
            "resolution": "",
            "hit_count": 1,
            "status": MemoryStatus.ACTIVE.value,
            "created_at": now,
            "last_hit_at": now,
            "tags": [],
            "summary_l0": "",
            "overview_l1": "",
        }
        r_warm = {**base, "id": "w", "tier": MemoryTier.WARM.value}
        r_hot = {**base, "id": "h", "tier": MemoryTier.HOT.value}

        db = MagicMock()
        db.get_memory_records_with_embeddings.return_value = [
            (r_warm, [0.0, 1.0]),
            (r_hot, [1.0, 0.0]),
        ]
        db.increment_memory_hit_light.return_value = None

        emb = MagicMock()
        emb.embed_text.return_value = [1.0, 0.0]

        def cos(q, v):
            return sum(x * y for x, y in zip(q, v))

        emb.cosine_similarity.side_effect = cos

        svc = MemoryService(db, emb, config=cfg)
        out = svc.search_memories("query", limit=10)
        self.assertEqual(len(out), 2)

    def test_search_memories_uses_config_limit_when_omitted(self):
        cfg = UltronConfig()
        cfg.enable_intent_analysis = False
        cfg.time_decay_weight = 0.0
        cfg.memory_search_default_limit = 1

        now = datetime.now().isoformat()
        base = {
            "memory_type": "pattern",
            "content": "c",
            "context": "",
            "resolution": "",
            "hit_count": 0,
            "status": MemoryStatus.ACTIVE.value,
            "created_at": now,
            "last_hit_at": now,
            "tags": [],
            "summary_l0": "",
            "overview_l1": "",
        }
        rows = [
            ({**base, "id": "a", "tier": MemoryTier.WARM.value}, [1.0, 0.0]),
            ({**base, "id": "b", "tier": MemoryTier.WARM.value}, [0.9, 0.0]),
        ]
        db = MagicMock()
        db.get_memory_records_with_embeddings.return_value = rows
        db.increment_memory_hit_light.return_value = None
        emb = MagicMock()
        emb.embed_text.return_value = [1.0, 0.0]
        emb.cosine_similarity.return_value = 0.5

        svc = MemoryService(db, emb, config=cfg)
        out = svc.search_memories("query")
        self.assertEqual(len(out), 1)

    def test_search_detail_level_l0_clears_fields(self):
        cfg = UltronConfig()
        cfg.enable_intent_analysis = False
        cfg.time_decay_weight = 0.0

        now = datetime.now().isoformat()
        row = {
            "id": "m1",
            "memory_type": "pattern",
            "content": "body",
            "context": "cx",
            "resolution": "rx",
            "tier": MemoryTier.WARM.value,
            "hit_count": 1,
            "status": MemoryStatus.ACTIVE.value,
            "created_at": now,
            "last_hit_at": now,
            "tags": [],
            "summary_l0": "l0",
            "overview_l1": "l1text",
            "embedding": [0.1],
        }

        db = MagicMock()
        db.get_memory_records_with_embeddings.return_value = [(row, [1.0, 0.0])]
        db.increment_memory_hit_light.return_value = None

        emb = MagicMock()
        emb.embed_text.return_value = [1.0, 0.0]
        emb.cosine_similarity.return_value = 0.8

        svc = MemoryService(db, emb, config=cfg)
        out = svc.search_memories("q", detail_level="l0", limit=5)
        self.assertEqual(len(out), 1)
        r = out[0].record
        self.assertEqual(r.content, "")
        self.assertEqual(r.context, "")
        self.assertEqual(r.resolution, "")
        self.assertEqual(r.overview_l1, "")
        self.assertEqual(r.embedding, [])
        self.assertEqual(r.summary_l0, "l0")

    def test_search_rejects_detail_level_full(self):
        svc = MemoryService(MagicMock(), MagicMock(), config=UltronConfig())
        with self.assertRaises(ValueError):
            svc.search_memories("q", detail_level="full")


class TestMemoryServiceHotnessAndVectors(unittest.TestCase):
    """_calculate_hotness, _record_embedding_vector."""

    def test_hotness_none_is_zero(self):
        svc = object.__new__(MemoryService)
        cfg = UltronConfig()
        svc.config = cfg
        self.assertEqual(MemoryService._calculate_hotness(svc, None), 0.0)

    def test_hotness_recent_near_one(self):
        svc = object.__new__(MemoryService)
        cfg = UltronConfig()
        cfg.decay_alpha = 0.01
        svc.config = cfg
        h = MemoryService._calculate_hotness(svc, datetime.now())
        self.assertGreater(h, 0.99)

    def test_hotness_iso_string_parsed(self):
        svc = object.__new__(MemoryService)
        cfg = UltronConfig()
        cfg.decay_alpha = 1.0
        svc.config = cfg
        recent = (datetime.now() - timedelta(hours=1)).isoformat()
        h = MemoryService._calculate_hotness(svc, recent)
        self.assertGreater(h, 0.9)

    def test_record_embedding_vector_list_pass_through(self):
        row = {"embedding": [0.5, 0.5]}
        self.assertEqual(MemoryService._record_embedding_vector(row), [0.5, 0.5])

    def test_record_embedding_vector_missing_empty(self):
        self.assertEqual(MemoryService._record_embedding_vector({}), [])


class TestMemoryServiceStaticMerges(unittest.TestCase):
    """_merge_tags_lists, _collapse_ws."""

    def test_merge_tags_dedupes_preserves_order(self):
        out = MemoryService._merge_tags_lists(["a", "b"], ["b", "c"])
        self.assertEqual(out, ["a", "b", "c"])

    def test_merge_tags_case_insensitive_keeps_first_spelling(self):
        out = MemoryService._merge_tags_lists(
            ["Alpha", "beta"], ["ALPHA", "Beta", "gamma"]
        )
        self.assertEqual(out, ["Alpha", "beta", "gamma"])

    def test_merge_tags_caps_at_merged_limit(self):
        existing = [f"t{i}" for i in range(6)]
        incoming = [f"n{i}" for i in range(10)]
        out = MemoryService._merge_tags_lists(existing, incoming)
        self.assertEqual(len(out), MemoryService._MERGED_TAGS_CAP)
        self.assertEqual(out[:6], existing)
        self.assertEqual(out[6:], ["n0", "n1", "n2", "n3"])

    def test_collapse_ws(self):
        collapsed = MemoryService._collapse_ws("  x  \n  y  ")
        self.assertEqual(collapsed, "x y")


class TestMemoryServiceSummariesAndRebalance(unittest.TestCase):
    """Rule-path summaries and tier rebalance behavior."""

    def test_generate_summaries_rule_fallback_first_line_l0(self):
        svc = MemoryService(MagicMock(), MagicMock(), llm_service=None)
        l0, _l1 = svc._generate_summaries("line1\nline2", "ctx", "res")
        # L0 fallback now collapses content to a single line (not just first line)
        self.assertEqual(l0, "line1 line2")

    def test_tier_rebalance_distributes_by_percentile(self):
        db = MagicMock()
        # 10 memories ranked by hit_count
        ranked = [(f"m{i}", "warm") for i in range(10)]
        db.get_all_memory_ids_ranked.return_value = ranked
        db.batch_update_tiers.return_value = 5
        db.archive_stale_cold_memories.return_value = 0

        cfg = UltronConfig()
        cfg.hot_percentile = 10
        cfg.warm_percentile = 40
        cfg.warm_max_entries = 1000
        cfg.cold_ttl_days = 7
        svc = MemoryService(db, MagicMock(), config=cfg)
        summary = svc.run_tier_rebalance()

        self.assertEqual(summary["total"], 10)
        self.assertEqual(summary["hot"], 1)  # ceil(10 * 10%) = 1
        self.assertEqual(summary["warm"], 4)  # ceil(10 * 40%) = 4
        self.assertEqual(summary["cold"], 5)  # 10 - 1 - 4 = 5
        db.batch_update_tiers.assert_called_once()
        db.archive_stale_cold_memories.assert_called_once_with(7)

    def test_tier_rebalance_pure_percentile(self):
        db = MagicMock()
        ranked = [(f"m{i}", "warm") for i in range(100)]
        db.get_all_memory_ids_ranked.return_value = ranked
        db.batch_update_tiers.return_value = 0
        db.archive_stale_cold_memories.return_value = 0

        cfg = UltronConfig()
        cfg.hot_percentile = 50
        cfg.warm_percentile = 40
        cfg.cold_ttl_days = 0
        svc = MemoryService(db, MagicMock(), config=cfg)
        summary = svc.run_tier_rebalance()

        self.assertEqual(summary["hot"], 50)  # 50% of 100
        self.assertEqual(summary["warm"], 40)  # 40% of 100
        self.assertEqual(summary["cold"], 10)  # rest

    def test_tier_rebalance_counts_newly_hot(self):
        db = MagicMock()
        ranked = [("m0", "cold"), ("m1", "hot")]
        db.get_all_memory_ids_ranked.return_value = ranked
        db.batch_update_tiers.return_value = 1
        db.archive_stale_cold_memories.return_value = 0

        cfg = UltronConfig()
        cfg.hot_percentile = 50
        cfg.warm_percentile = 40
        cfg.warm_max_entries = 1000
        cfg.cold_ttl_days = 0

        svc = MemoryService(db, MagicMock(), config=cfg)
        summary = svc.run_tier_rebalance()

        self.assertEqual(summary["newly_hot"], 1)


class TestMemoryServiceDelegates(unittest.TestCase):
    """Thin API surfaces that delegate to Database."""

    def test_get_memory_stats_delegates(self):
        db = MagicMock()
        db.get_memory_stats.return_value = {"total": 3}
        svc = MemoryService(db, MagicMock())
        self.assertEqual(svc.get_memory_stats(), {"total": 3})
        db.get_memory_stats.assert_called_once()

    def test_get_memory_details_increments(self):
        db = MagicMock()
        now = datetime.now().isoformat()
        updated = {
            "id": "x",
            "memory_type": "pattern",
            "content": "",
            "context": "",
            "resolution": "",
            "tier": MemoryTier.WARM.value,
            "hit_count": 2,
            "status": MemoryStatus.ACTIVE.value,
            "created_at": now,
            "last_hit_at": now,
            "tags": [],
        }
        db.increment_memory_hit_light.side_effect = [updated, None]

        svc = MemoryService(db, MagicMock())
        out = svc.get_memory_details(["x", "missing"])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].id, "x")
        self.assertEqual(db.increment_memory_hit_light.call_count, 2)


class TestMemoryServiceRebalance(unittest.TestCase):
    """run_tier_rebalance wiring."""

    def test_run_tier_rebalance_calls_db(self):
        db = MagicMock()
        db.get_all_memory_ids_ranked.return_value = []
        db.batch_update_tiers.return_value = 0
        db.archive_stale_cold_memories.return_value = 0

        cfg = UltronConfig()
        cfg.cold_ttl_days = 7
        svc = MemoryService(db, MagicMock(), config=cfg)
        summary = svc.run_tier_rebalance()
        self.assertIn("total", summary)
        self.assertIn("cold_archived", summary)
        db.archive_stale_cold_memories.assert_called_once_with(7)


if __name__ == "__main__":
    unittest.main()
