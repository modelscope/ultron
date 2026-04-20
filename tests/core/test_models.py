# Copyright (c) ModelScope Contributors. All rights reserved.
import unittest
from datetime import datetime

from ultron.core.models import (
    EvolutionRecord,
    KnowledgeCluster,
    MemoryRecord,
    MemoryTier,
    MemoryType,
    Skill,
    SkillFrontmatter,
    SkillMeta,
    SkillUsageRecord,
)


class TestSkillMeta(unittest.TestCase):
    def test_roundtrip_dict(self):
        m = SkillMeta(owner_id="o", slug="s", version="1.0.0", published_at=42)
        d = m.to_dict()
        self.assertEqual(d["slug"], "s")
        m2 = SkillMeta.from_dict(d)
        self.assertEqual(m2.slug, "s")

    def test_to_dict_includes_evolution_fields(self):
        m = SkillMeta(
            owner_id="o", slug="s", version="1.0.0", published_at=0,
            cluster_id="cid", evolution_count=3, structure_score=0.85,
        )
        d = m.to_dict()
        self.assertEqual(d["clusterId"], "cid")
        self.assertEqual(d["evolutionCount"], 3)
        self.assertAlmostEqual(d["structureScore"], 0.85)

    def test_from_dict_defaults(self):
        m = SkillMeta.from_dict({})
        self.assertEqual(m.version, "1.0.0")
        self.assertEqual(m.evolution_count, 0)
        self.assertIsNone(m.structure_score)

    def test_to_json_is_valid(self):
        import json
        m = SkillMeta(owner_id="o", slug="s", version="1.0.0", published_at=0)
        parsed = json.loads(m.to_json())
        self.assertEqual(parsed["slug"], "s")


class TestMemoryRecord(unittest.TestCase):
    def test_to_dict_embedding_toggle(self):
        now = datetime.now()
        r = MemoryRecord(
            id="i", memory_type="pattern", content="c", context="",
            resolution="", tier="warm", hit_count=1, status="active",
            created_at=now, last_hit_at=now, embedding=[0.1],
        )
        self.assertIn("embedding", r.to_dict())
        self.assertNotIn("embedding", r.to_dict(include_embedding=False))

    def test_from_dict_tags_json_string(self):
        now = datetime.now().isoformat()
        r = MemoryRecord.from_dict({
            "id": "x", "memory_type": "pattern", "content": "",
            "context": "", "resolution": "", "tier": "warm",
            "hit_count": 1, "status": "active",
            "created_at": now, "last_hit_at": now,
            "tags": '["a","b"]',
        })
        self.assertEqual(r.tags, ["a", "b"])

    def test_from_dict_tags_list(self):
        now = datetime.now().isoformat()
        r = MemoryRecord.from_dict({
            "id": "x", "memory_type": "pattern", "content": "",
            "context": "", "resolution": "", "tier": "warm",
            "hit_count": 1, "status": "active",
            "created_at": now, "last_hit_at": now,
            "tags": ["x", "y"],
        })
        self.assertEqual(r.tags, ["x", "y"])

    def test_to_dict_includes_summaries(self):
        now = datetime.now()
        r = MemoryRecord(
            id="i", memory_type="pattern", content="c", context="",
            resolution="", tier="hot", hit_count=5, status="active",
            created_at=now, last_hit_at=now,
            summary_l0="short", overview_l1="longer overview",
        )
        d = r.to_dict()
        self.assertEqual(d["summary_l0"], "short")
        self.assertEqual(d["overview_l1"], "longer overview")

    def test_from_dict_missing_optional_fields(self):
        now = datetime.now().isoformat()
        r = MemoryRecord.from_dict({
            "id": "x", "memory_type": "error", "content": "c",
            "context": "", "resolution": "", "tier": "cold",
            "hit_count": 0, "status": "active",
            "created_at": now, "last_hit_at": now,
        })
        self.assertEqual(r.embedding, [])
        self.assertEqual(r.tags, [])


class TestSkillUsageRecord(unittest.TestCase):
    def test_roundtrip(self):
        now = datetime.now()
        u = SkillUsageRecord(
            id="u", skill_slug="slug", skill_version="1.0.0",
            task_id="t", success=True, used_at=now,
        )
        u2 = SkillUsageRecord.from_dict(u.to_dict())
        self.assertEqual(u2.skill_slug, "slug")
        self.assertTrue(u2.success)

    def test_roundtrip_failure(self):
        now = datetime.now()
        u = SkillUsageRecord(
            id="u2", skill_slug="s", skill_version="1.0.0",
            task_id="t", success=False, used_at=now,
            feedback="something failed",
        )
        d = u.to_dict()
        u2 = SkillUsageRecord.from_dict(d)
        self.assertFalse(u2.success)
        self.assertEqual(u2.feedback, "something failed")


class TestSkillFrontmatter(unittest.TestCase):
    def test_ultron_metadata_categories(self):
        f = SkillFrontmatter(
            name="n", description="d",
            metadata={"ultron": {"categories": ["x"], "complexity": "low"}},
        )
        self.assertEqual(f.categories, ["x"])
        self.assertEqual(f.complexity, "low")

    def test_default_complexity(self):
        f = SkillFrontmatter(name="n", description="d", metadata={})
        self.assertEqual(f.complexity, "medium")

    def test_default_categories(self):
        f = SkillFrontmatter(name="n", description="d", metadata={})
        self.assertEqual(f.categories, [])

    def test_source_type(self):
        f = SkillFrontmatter(
            name="n", description="d",
            metadata={"ultron": {"source_type": "evolution"}},
        )
        self.assertEqual(f.source_type, "evolution")

    def test_roundtrip_from_dict(self):
        f = SkillFrontmatter(
            name="Test", description="desc",
            metadata={"ultron": {"categories": ["ai-llms"]}},
        )
        f2 = SkillFrontmatter.from_dict(f.to_dict())
        self.assertEqual(f2.name, "Test")
        self.assertEqual(f2.categories, ["ai-llms"])


class TestSkillModel(unittest.TestCase):
    def _make_skill(self, slug="s", version="1.0.0"):
        meta = SkillMeta(owner_id="o", slug=slug, version=version, published_at=0)
        front = SkillFrontmatter(
            name="My Skill", description="desc",
            metadata={"ultron": {"categories": ["general"], "complexity": "high"}},
        )
        return Skill(meta=meta, frontmatter=front, content="# Content", scripts={})

    def test_full_id(self):
        sk = self._make_skill("my-skill", "2.0.0")
        self.assertEqual(sk.full_id, "my-skill-2.0.0")

    def test_name_description_proxy(self):
        sk = self._make_skill()
        self.assertEqual(sk.name, "My Skill")
        self.assertEqual(sk.description, "desc")

    def test_categories_proxy(self):
        sk = self._make_skill()
        self.assertEqual(sk.categories, ["general"])

    def test_complexity_proxy(self):
        sk = self._make_skill()
        self.assertEqual(sk.complexity, "high")


class TestKnowledgeCluster(unittest.TestCase):
    def test_size_from_memory_ids(self):
        c = KnowledgeCluster(
            cluster_id="cid", topic="t", centroid=[],
            memory_ids=["m1", "m2", "m3"],
        )
        self.assertEqual(c.size, 3)

    def test_to_dict_roundtrip(self):
        now = datetime.now()
        c = KnowledgeCluster(
            cluster_id="cid", topic="topic", centroid=[0.1, 0.2],
            memory_ids=["m1"], skill_slug="s1",
            superseded_slugs=["old-s"],
            created_at=now, last_updated_at=now,
        )
        d = c.to_dict()
        c2 = KnowledgeCluster.from_dict(d)
        self.assertEqual(c2.cluster_id, "cid")
        self.assertEqual(c2.skill_slug, "s1")
        self.assertEqual(c2.superseded_slugs, ["old-s"])

    def test_from_dict_json_string_memory_ids(self):
        import json
        c = KnowledgeCluster.from_dict({
            "cluster_id": "x", "topic": "t",
            "memory_ids": json.dumps(["a", "b"]),
            "skill_slug": None, "superseded_slugs": "[]",
        })
        self.assertEqual(c.memory_ids, ["a", "b"])


class TestEvolutionRecord(unittest.TestCase):
    def test_to_dict(self):
        now = datetime.now()
        r = EvolutionRecord(
            id="eid", skill_slug="s", cluster_id="cid",
            timestamp=now, old_version="1.0.0", new_version="1.1.0",
            old_score=0.5, new_score=0.8, status="recrystallized",
            trigger="new_memory", memory_count=5,
            new_memory_ids=["m1"], superseded_skills=[],
            mutation_summary="Added 2 steps",
        )
        d = r.to_dict()
        self.assertEqual(d["status"], "recrystallized")
        self.assertEqual(d["new_score"], 0.8)
        self.assertIn("m1", d["new_memory_ids"])


class TestMemoryEnums(unittest.TestCase):
    def test_memory_tier_values(self):
        self.assertEqual(MemoryTier.HOT.value, "hot")
        self.assertEqual(MemoryTier.WARM.value, "warm")
        self.assertEqual(MemoryTier.COLD.value, "cold")

    def test_memory_type_values(self):
        self.assertEqual(MemoryType.ERROR.value, "error")
        self.assertEqual(MemoryType.SECURITY.value, "security")
        self.assertEqual(MemoryType.PATTERN.value, "pattern")


if __name__ == "__main__":
    unittest.main()

