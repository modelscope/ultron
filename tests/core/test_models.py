# Copyright (c) ModelScope Contributors. All rights reserved.
import unittest
from datetime import datetime

from ultron.core.models import (
    MemoryRecord,
    SkillFrontmatter,
    SkillMeta,
    SkillStatus,
    SkillUsageRecord,
)


class TestSkillMeta(unittest.TestCase):
    def test_roundtrip_dict(self):
        m = SkillMeta(
            owner_id="o",
            slug="s",
            version="1.0.0",
            published_at=42,
            status=SkillStatus.ACTIVE,
        )
        d = m.to_dict()
        self.assertEqual(d["slug"], "s")
        m2 = SkillMeta.from_dict(d)
        self.assertEqual(m2.slug, "s")
        self.assertEqual(m2.status, SkillStatus.ACTIVE)


class TestMemoryRecord(unittest.TestCase):
    def test_to_dict_embedding_toggle(self):
        now = datetime.now()
        r = MemoryRecord(
            id="i",
            memory_type="pattern",
            content="c",
            context="",
            resolution="",
            tier="warm",
            hit_count=1,
            status="active",
            created_at=now,
            last_hit_at=now,
            embedding=[0.1],
        )
        self.assertIn("embedding", r.to_dict())
        self.assertNotIn("embedding", r.to_dict(include_embedding=False))

    def test_from_dict_tags_json_string(self):
        now = datetime.now().isoformat()
        r = MemoryRecord.from_dict({
            "id": "x",
            "memory_type": "pattern",
            "content": "",
            "context": "",
            "resolution": "",
            "tier": "warm",
            "hit_count": 1,
            "status": "active",
            "created_at": now,
            "last_hit_at": now,
            "tags": '["a","b"]',
        })
        self.assertEqual(r.tags, ["a", "b"])


class TestSkillUsageRecord(unittest.TestCase):
    def test_roundtrip(self):
        now = datetime.now()
        u = SkillUsageRecord(
            id="u",
            skill_slug="slug",
            skill_version="1.0.0",
            task_id="t",
            success=True,
            used_at=now,
        )
        u2 = SkillUsageRecord.from_dict(u.to_dict())
        self.assertEqual(u2.skill_slug, "slug")


class TestSkillFrontmatter(unittest.TestCase):
    def test_ultron_metadata_categories(self):
        f = SkillFrontmatter(
            name="n",
            description="d",
            metadata={"ultron": {"categories": ["x"], "complexity": "low"}},
        )
        self.assertEqual(f.categories, ["x"])
        self.assertEqual(f.complexity, "low")


if __name__ == "__main__":
    unittest.main()
