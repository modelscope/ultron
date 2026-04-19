# Copyright (c) ModelScope Contributors. All rights reserved.
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from ultron.config import UltronConfig
from ultron.core.database import Database
from ultron.core.models import KnowledgeCluster, MemoryRecord, SkillMeta, SkillFrontmatter, Skill
from ultron.core.storage import SkillStorage
from ultron.services.skill.skill_cluster import KnowledgeClusterService
from ultron.services.skill.skill_evolution import SkillEvolutionEngine


def _make_cluster(cluster_id="cid-1", skill_slug=None, size=5) -> KnowledgeCluster:
    return KnowledgeCluster(
        cluster_id=cluster_id,
        topic="error handling patterns",
        centroid=[0.5] * 4,
        memory_ids=[f"mem-{i}" for i in range(size)],
        skill_slug=skill_slug,
        superseded_slugs=[],
    )


def _make_memory(mid: str) -> MemoryRecord:
    now = datetime.now()
    m = MemoryRecord(
        id=mid,
        memory_type="pattern",
        content=f"content for {mid}",
        context="ctx",
        resolution="res",
        tier="hot",
        hit_count=1,
        status="active",
        created_at=now,
        last_hit_at=now,
    )
    m.embedding = [0.5, 0.5, 0.0, 0.0]
    return m


def _make_skill(slug="test-skill", version="1.0.0", score=0.6) -> Skill:
    meta = SkillMeta(
        owner_id="ultron-evolution",
        slug=slug,
        version=version,
        published_at=0,
        structure_score=score,
        evolution_count=0,
    )
    frontmatter = SkillFrontmatter(
        name="Test Skill",
        description="A test skill",
        metadata={"ultron": {"categories": ["general"], "complexity": "medium"}},
    )
    return Skill(meta=meta, frontmatter=frontmatter, content="# Test\n\n1. Step one\n2. Step two\n3. Step three\n\nWhen to use: always\n\nError: handle exceptions", scripts={})


class TestSkillEvolutionStaticHelpers(unittest.TestCase):
    def test_slugify_basic(self):
        self.assertEqual(SkillEvolutionEngine._slugify("Error Handling"), "error-handling")

    def test_slugify_special_chars(self):
        self.assertEqual(SkillEvolutionEngine._slugify("foo!@#bar"), "foo-bar")

    def test_slugify_cjk(self):
        slug = SkillEvolutionEngine._slugify("错误处理")
        self.assertIn("错误处理", slug)

    def test_slugify_empty(self):
        self.assertEqual(SkillEvolutionEngine._slugify(""), "")

    def test_increment_version_minor(self):
        self.assertEqual(SkillEvolutionEngine._increment_version("1.0.0"), "1.1.0")
        self.assertEqual(SkillEvolutionEngine._increment_version("2.3.1"), "2.4.1")

    def test_increment_version_fallback(self):
        self.assertEqual(SkillEvolutionEngine._increment_version("bad"), "1.1.0")

    def test_verification_passed_no_verification(self):
        self.assertTrue(SkillEvolutionEngine._verification_passed(None))

    def test_verification_passed_high_grounded(self):
        v = {"grounded_in_evidence": 0.9, "has_contradiction": False}
        self.assertTrue(SkillEvolutionEngine._verification_passed(v))

    def test_verification_failed_low_grounded(self):
        v = {"grounded_in_evidence": 0.5, "has_contradiction": False}
        self.assertFalse(SkillEvolutionEngine._verification_passed(v))

    def test_verification_failed_contradiction(self):
        v = {"grounded_in_evidence": 0.95, "has_contradiction": True}
        self.assertFalse(SkillEvolutionEngine._verification_passed(v))

    def test_compute_structure_score_no_verification(self):
        score = SkillEvolutionEngine._compute_structure_score(None)
        self.assertAlmostEqual(score, 0.5)

    def test_compute_structure_score_with_values(self):
        v = {"workflow_clarity": 1.0, "specificity_and_reusability": 1.0, "preserves_existing_value": 1.0}
        score = SkillEvolutionEngine._compute_structure_score(v)
        self.assertAlmostEqual(score, 1.0)

    def test_compute_structure_score_partial(self):
        v = {"workflow_clarity": 0.5, "specificity_and_reusability": 0.5, "preserves_existing_value": 0.5}
        score = SkillEvolutionEngine._compute_structure_score(v)
        self.assertAlmostEqual(score, 0.5)


class TestSkillEvolutionQualityBar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db = Database(os.path.join(self.tmp.name, "test.db"))
        storage = SkillStorage(os.path.join(self.tmp.name, "skills"), os.path.join(self.tmp.name, "archive"))
        emb = MagicMock()
        emb.embed_skill.return_value = [0.1] * 4
        cluster_svc = MagicMock()
        self.engine = SkillEvolutionEngine(db, storage, emb, cluster_svc)

    def tearDown(self):
        self.tmp.cleanup()

    def test_quality_bar_fails_short_content(self):
        self.assertFalse(self.engine._meets_quality_bar("short"))

    def test_quality_bar_passes_rich_content(self):
        content = (
            "# Error Handling Skill\n\n"
            "When to use: when errors occur in production.\n\n"
            "1. Catch the exception\n"
            "2. Log the error details\n"
            "3. Return a fallback response\n\n"
            "Error: if the fallback also fails, escalate.\n"
            "Otherwise, retry up to 3 times.\n"
        ) * 5  # repeat to exceed token minimum
        self.assertTrue(self.engine._meets_quality_bar(content))

    def test_quality_bar_fails_missing_steps(self):
        # Has trigger keyword but no steps and no edge-case keywords — only 1 check
        content = "When to use this skill: always. " * 60
        self.assertFalse(self.engine._meets_quality_bar(content))


class TestSkillEvolutionCrystallize(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self.tmp.name, "test.db"))
        self.storage = SkillStorage(os.path.join(self.tmp.name, "skills"), os.path.join(self.tmp.name, "archive"))
        self.emb = MagicMock()
        self.emb.embed_skill.return_value = [0.1] * 4
        self.emb.embed_text.return_value = [0.1] * 4
        self.cluster_svc = MagicMock()
        self.llm = MagicMock()
        self.llm.llm._count_tokens.return_value = 500
        cfg = UltronConfig()
        cfg.crystallization_threshold = 3
        self.engine = SkillEvolutionEngine(
            self.db, self.storage, self.emb, self.cluster_svc,
            config=cfg, llm_orchestrator=self.llm,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _good_content(self):
        return (
            "# Error Handling\n\nWhen to use: on any exception.\n\n"
            "1. Catch exception\n2. Log it\n3. Return fallback\n\n"
            "Error: if fallback fails, escalate.\nOtherwise retry.\n"
        ) * 6

    def test_crystallize_below_threshold_returns_none(self):
        cluster = _make_cluster(size=2)
        self.cluster_svc.get_cluster_memories.return_value = [_make_memory(f"m{i}") for i in range(2)]
        result = self.engine.crystallize_cluster(cluster)
        self.assertIsNone(result)

    def test_crystallize_llm_insufficient_returns_none(self):
        cluster = _make_cluster(size=5)
        self.cluster_svc.get_cluster_memories.return_value = [_make_memory(f"m{i}") for i in range(5)]
        self.llm.crystallize_skill_from_cluster.return_value = {"quality": "insufficient"}
        result = self.engine.crystallize_cluster(cluster)
        self.assertIsNone(result)

    def test_crystallize_llm_none_returns_none(self):
        cluster = _make_cluster(size=5)
        self.cluster_svc.get_cluster_memories.return_value = [_make_memory(f"m{i}") for i in range(5)]
        self.llm.crystallize_skill_from_cluster.return_value = None
        result = self.engine.crystallize_cluster(cluster)
        self.assertIsNone(result)

    def test_crystallize_quality_gate_fails_returns_none(self):
        cluster = _make_cluster(size=5)
        self.cluster_svc.get_cluster_memories.return_value = [_make_memory(f"m{i}") for i in range(5)]
        self.llm.crystallize_skill_from_cluster.return_value = {
            "name": "Test", "description": "desc", "content": "too short",
        }
        result = self.engine.crystallize_cluster(cluster)
        self.assertIsNone(result)

    def test_crystallize_verification_fails_returns_none(self):
        cluster = _make_cluster(size=5)
        self.cluster_svc.get_cluster_memories.return_value = [_make_memory(f"m{i}") for i in range(5)]
        self.llm.crystallize_skill_from_cluster.return_value = {
            "name": "Test", "description": "desc", "content": self._good_content(),
        }
        self.llm.verify_skill.return_value = {"grounded_in_evidence": 0.3, "has_contradiction": False}
        result = self.engine.crystallize_cluster(cluster)
        self.assertIsNone(result)

    def test_crystallize_success(self):
        cluster = _make_cluster(size=5)
        self.cluster_svc.get_cluster_memories.return_value = [_make_memory(f"m{i}") for i in range(5)]
        self.llm.crystallize_skill_from_cluster.return_value = {
            "name": "Error Handling", "description": "Handle errors", "content": self._good_content(),
        }
        self.llm.verify_skill.return_value = {
            "grounded_in_evidence": 0.95,
            "has_contradiction": False,
            "workflow_clarity": 0.9,
            "specificity_and_reusability": 0.85,
            "preserves_existing_value": 1.0,
        }
        result = self.engine.crystallize_cluster(cluster)
        self.assertIsNotNone(result)
        self.assertEqual(result.meta.version, "1.0.0")
        self.assertIn("error-handling", result.meta.slug)

    def test_crystallize_generates_topic_when_missing(self):
        cluster = _make_cluster(size=5)
        cluster.topic = ""
        self.cluster_svc.get_cluster_memories.return_value = [_make_memory(f"m{i}") for i in range(5)]
        self.llm.generate_cluster_topic.return_value = "generated topic"
        self.llm.crystallize_skill_from_cluster.return_value = {"quality": "insufficient"}
        self.engine.crystallize_cluster(cluster)
        self.llm.generate_cluster_topic.assert_called_once()


class TestSkillEvolutionRecrystallize(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self.tmp.name, "test.db"))
        self.storage = SkillStorage(os.path.join(self.tmp.name, "skills"), os.path.join(self.tmp.name, "archive"))
        self.emb = MagicMock()
        self.emb.embed_skill.return_value = [0.1] * 4
        self.cluster_svc = MagicMock()
        self.llm = MagicMock()
        self.llm.llm._count_tokens.return_value = 500
        cfg = UltronConfig()
        cfg.crystallization_threshold = 3
        cfg.recrystallization_delta = 2
        self.engine = SkillEvolutionEngine(
            self.db, self.storage, self.emb, self.cluster_svc,
            config=cfg, llm_orchestrator=self.llm,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _save_skill(self, slug="test-skill", version="1.0.0", score=0.6):
        skill = _make_skill(slug, version, score)
        self.storage.save_skill(skill)
        self.db.save_skill(skill.meta, skill.frontmatter, f"/tmp/{slug}")
        return skill

    def test_recrystallize_no_skill_slug_returns_none(self):
        cluster = _make_cluster(skill_slug=None)
        result = self.engine.recrystallize_skill(cluster)
        self.assertIsNone(result)

    def test_recrystallize_skill_not_in_db_returns_none(self):
        cluster = _make_cluster(skill_slug="nonexistent")
        result = self.engine.recrystallize_skill(cluster)
        self.assertIsNone(result)

    def test_recrystallize_llm_unnecessary_returns_none(self):
        skill = self._save_skill()
        cluster = _make_cluster(skill_slug=skill.meta.slug)
        self.cluster_svc.get_cluster_memories.return_value = [_make_memory(f"m{i}") for i in range(5)]
        self.db.count_cluster_members_since = MagicMock(return_value=2)
        self.llm.recrystallize_skill.return_value = {"evolution": "unnecessary"}
        result = self.engine.recrystallize_skill(cluster)
        self.assertIsNone(result)

    def test_recrystallize_upgrade_gate_rejects_lower_score(self):
        skill = self._save_skill(score=0.8)
        cluster = _make_cluster(skill_slug=skill.meta.slug)
        self.cluster_svc.get_cluster_memories.return_value = [_make_memory(f"m{i}") for i in range(5)]
        self.db.count_cluster_members_since = MagicMock(return_value=2)
        good_content = (
            "# Skill\n\nWhen to use: always.\n\n"
            "1. Step one\n2. Step two\n3. Step three\n\n"
            "Error: handle exceptions.\nOtherwise fallback.\n"
        ) * 6
        self.llm.recrystallize_skill.return_value = {
            "name": "Test Skill", "description": "desc", "content": good_content,
        }
        # Verification gives lower score than existing 0.8
        self.llm.verify_skill.return_value = {
            "grounded_in_evidence": 0.9,
            "has_contradiction": False,
            "workflow_clarity": 0.4,
            "specificity_and_reusability": 0.4,
            "preserves_existing_value": 0.4,
        }
        result = self.engine.recrystallize_skill(cluster)
        self.assertIsNone(result)

    def test_recrystallize_success_increments_version(self):
        skill = self._save_skill(score=0.5)
        cluster = _make_cluster(skill_slug=skill.meta.slug)
        self.cluster_svc.get_cluster_memories.return_value = [_make_memory(f"m{i}") for i in range(5)]
        self.db.count_cluster_members_since = MagicMock(return_value=2)
        good_content = (
            "# Skill\n\nWhen to use: always.\n\n"
            "1. Step one\n2. Step two\n3. Step three\n\n"
            "Error: handle exceptions.\nOtherwise fallback.\n"
        ) * 6
        self.llm.recrystallize_skill.return_value = {
            "name": "Test Skill", "description": "desc", "content": good_content,
        }
        self.llm.verify_skill.return_value = {
            "grounded_in_evidence": 0.95,
            "has_contradiction": False,
            "workflow_clarity": 0.9,
            "specificity_and_reusability": 0.9,
            "preserves_existing_value": 1.0,
        }
        result = self.engine.recrystallize_skill(cluster)
        self.assertIsNotNone(result)
        self.assertEqual(result.meta.version, "1.1.0")
        self.assertEqual(result.meta.evolution_count, 1)


class TestSkillEvolutionRunCycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self.tmp.name, "test.db"))
        self.storage = SkillStorage(os.path.join(self.tmp.name, "skills"), os.path.join(self.tmp.name, "archive"))
        self.emb = MagicMock()
        self.cluster_svc = MagicMock()
        self.llm = MagicMock()
        self.llm.llm._count_tokens.return_value = 500
        cfg = UltronConfig()
        cfg.evolution_enabled = True
        cfg.evolution_batch_limit = 5
        self.engine = SkillEvolutionEngine(
            self.db, self.storage, self.emb, self.cluster_svc,
            config=cfg, llm_orchestrator=self.llm,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_cycle_disabled(self):
        self.engine.config.evolution_enabled = False
        result = self.engine.run_evolution_cycle()
        self.assertTrue(result.get("skipped"))

    def test_run_cycle_no_clusters(self):
        self.cluster_svc.get_clusters_ready_to_crystallize.return_value = []
        self.cluster_svc.get_clusters_ready_to_recrystallize.return_value = []
        result = self.engine.run_evolution_cycle()
        self.assertEqual(result["crystallized"], 0)
        self.assertEqual(result["recrystallized"], 0)

    def test_run_cycle_respects_batch_limit(self):
        clusters = [_make_cluster(f"cid-{i}", size=5) for i in range(10)]
        self.cluster_svc.get_clusters_ready_to_crystallize.return_value = clusters
        self.cluster_svc.get_clusters_ready_to_recrystallize.return_value = []
        self.cluster_svc.get_cluster_memories.return_value = []
        # crystallize_cluster will return None for all (no memories)
        result = self.engine.run_evolution_cycle(limit=3)
        # Only 3 clusters attempted
        self.assertEqual(self.cluster_svc.get_cluster_memories.call_count, 3)


if __name__ == "__main__":
    unittest.main()
