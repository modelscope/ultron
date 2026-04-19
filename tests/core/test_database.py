# Copyright (c) ModelScope Contributors. All rights reserved.
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from ultron.core.database import Database
from ultron.core.models import MemoryRecord, SkillFrontmatter, SkillMeta


def _make_db(tmp: str) -> Database:
    return Database(str(Path(tmp) / "test.db"))


def _make_memory(mid: str, tier: str = "warm") -> MemoryRecord:
    now = datetime.now()
    return MemoryRecord(
        id=mid, memory_type="pattern", content=f"content {mid}",
        context="ctx", resolution="res", tier=tier,
        hit_count=1, status="active", created_at=now, last_hit_at=now,
    )


class TestCatalogSkillMixin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = _make_db(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_bulk_upsert_and_query(self):
        skills = [
            {"full_name": "@ns/skill-a", "name": "skill-a", "display_name": "Skill A",
             "path": "@ns", "description": "描述A", "description_en": "Description A",
             "owner": "owner1", "category_id": "dev-tools", "category_name": "开发工具",
             "embedding": [0.1, 0.2, 0.3]},
            {"full_name": "@ns/skill-b", "name": "skill-b", "display_name": "Skill B",
             "path": "@ns", "description": "描述B", "description_en": "Description B",
             "owner": "owner2", "category_id": "ai-media", "category_name": "媒体处理",
             "embedding": [0.4, 0.5, 0.6]},
        ]
        count = self.db.bulk_upsert_catalog_skills(skills)
        self.assertEqual(count, 2)
        s = self.db.get_catalog_skill("@ns/skill-a")
        self.assertIsNotNone(s)
        self.assertEqual(s["display_name"], "Skill A")
        self.assertIsNone(self.db.get_catalog_skill("@ns/missing"))

    def test_get_catalog_skills_with_embeddings(self):
        skills = [
            {"full_name": "@ns/with-emb", "name": "with-emb", "embedding": [1.0, 0.0]},
            {"full_name": "@ns/no-emb", "name": "no-emb", "embedding": None},
        ]
        self.db.bulk_upsert_catalog_skills(skills)
        results = self.db.get_catalog_skills_with_embeddings()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0]["full_name"], "@ns/with-emb")

    def test_upsert_is_idempotent(self):
        skill = {"full_name": "@ns/skill-x", "name": "skill-x", "description": "v1", "embedding": [1.0]}
        self.db.bulk_upsert_catalog_skills([skill])
        skill["description"] = "v2"
        self.db.bulk_upsert_catalog_skills([skill])
        s = self.db.get_catalog_skill("@ns/skill-x")
        self.assertEqual(s["description"], "v2")

    def test_get_catalog_stats(self):
        skills = [
            {"full_name": "@a/s1", "name": "s1", "category_id": "dev", "category_name": "Dev", "embedding": [1.0]},
            {"full_name": "@a/s2", "name": "s2", "category_id": "dev", "category_name": "Dev", "embedding": [1.0]},
            {"full_name": "@a/s3", "name": "s3", "category_id": "ai", "category_name": "AI", "embedding": None},
        ]
        self.db.bulk_upsert_catalog_skills(skills)
        stats = self.db.get_catalog_stats()
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["with_embedding"], 2)
        self.assertEqual(len(stats["categories"]), 2)

    def test_empty_bulk_upsert(self):
        self.assertEqual(self.db.bulk_upsert_catalog_skills([]), 0)


class TestMemoryMixin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = _make_db(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_and_get_memory_record(self):
        m = _make_memory("m1")
        self.db.save_memory_record(m)
        row = self.db.get_memory_record("m1")
        self.assertIsNotNone(row)
        self.assertEqual(row["content"], "content m1")

    def test_get_memory_record_missing(self):
        self.assertIsNone(self.db.get_memory_record("nonexistent"))

    def test_get_memory_records_by_tier(self):
        self.db.save_memory_record(_make_memory("m1", "hot"))
        self.db.save_memory_record(_make_memory("m2", "warm"))
        self.db.save_memory_record(_make_memory("m3", "hot"))
        hot = self.db.get_memory_records_by_tier("hot")
        self.assertEqual(len(hot), 2)
        warm = self.db.get_memory_records_by_tier("warm")
        self.assertEqual(len(warm), 1)

    def test_increment_memory_hit(self):
        m = _make_memory("m1")
        self.db.save_memory_record(m)
        self.db.increment_memory_hit("m1")
        row = self.db.get_memory_record("m1")
        self.assertEqual(row["hit_count"], 2)

    def test_increment_memory_hit_light(self):
        m = _make_memory("m1")
        self.db.save_memory_record(m)
        self.db.increment_memory_hit_light("m1", weight=3)
        row = self.db.get_memory_record("m1")
        self.assertEqual(row["hit_count"], 4)

    def test_update_memory_tier(self):
        m = _make_memory("m1", "warm")
        self.db.save_memory_record(m)
        self.db.update_memory_tier("m1", "hot")
        row = self.db.get_memory_record("m1")
        self.assertEqual(row["tier"], "hot")

    def test_update_memory_status(self):
        m = _make_memory("m1")
        self.db.save_memory_record(m)
        self.db.update_memory_status("m1", "archived")
        row = self.db.get_memory_record("m1")
        self.assertEqual(row["status"], "archived")

    def test_update_memory_merged_body(self):
        m = _make_memory("m1")
        self.db.save_memory_record(m)
        ok = self.db.update_memory_merged_body(
            "m1", "new content", "new ctx", "new res",
            [0.1, 0.2], "l0 summary", "l1 overview",
        )
        self.assertTrue(ok)
        row = self.db.get_memory_record("m1")
        self.assertEqual(row["content"], "new content")
        self.assertEqual(row["summary_l0"], "l0 summary")

    def test_get_memory_records_with_embeddings(self):
        m1 = _make_memory("m1")
        m1.embedding = [0.1, 0.2]
        m2 = _make_memory("m2")
        self.db.save_memory_record(m1)
        self.db.save_memory_record(m2)
        results = self.db.get_memory_records_with_embeddings()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0]["id"], "m1")

    def test_get_memory_contributions(self):
        m = _make_memory("m1")
        self.db.save_memory_record(m)
        self.db.increment_memory_hit("m1", content="contrib content", context="ctx")
        contribs = self.db.get_memory_contributions("m1")
        self.assertEqual(len(contribs), 1)
        self.assertEqual(contribs[0]["content"], "contrib content")


class TestSkillMixin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = _make_db(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _make_skill_meta(self, slug="s", version="1.0.0"):
        return SkillMeta(owner_id="o", slug=slug, version=version, published_at=0)

    def _make_frontmatter(self, name="Test"):
        return SkillFrontmatter(
            name=name, description="desc",
            metadata={"ultron": {"categories": ["general"], "complexity": "low"}},
        )

    def test_save_and_get_skill(self):
        meta = self._make_skill_meta()
        front = self._make_frontmatter()
        self.db.save_skill(meta, front, "/tmp/s")
        row = self.db.get_skill("s")
        self.assertIsNotNone(row)
        self.assertEqual(row["slug"], "s")
        self.assertEqual(row["name"], "Test")

    def test_get_skill_missing(self):
        self.assertIsNone(self.db.get_skill("nonexistent"))

    def test_get_skill_by_version(self):
        meta = self._make_skill_meta(version="2.0.0")
        front = self._make_frontmatter()
        self.db.save_skill(meta, front)
        row = self.db.get_skill("s", version="2.0.0")
        self.assertIsNotNone(row)
        self.assertIsNone(self.db.get_skill("s", version="9.9.9"))

    def test_get_all_skills(self):
        for i in range(3):
            self.db.save_skill(self._make_skill_meta(f"s{i}"), self._make_frontmatter(f"Skill{i}"))
        skills = self.db.get_all_skills()
        self.assertEqual(len(skills), 3)

    def test_save_category(self):
        self.db.save_category("web-frontend", "Web dev")
        cats = self.db.get_all_categories()
        names = [c["name"] for c in cats]
        self.assertIn("web-frontend", names)

    def test_search_skills_by_text(self):
        meta = self._make_skill_meta("react-skill")
        front = SkillFrontmatter(name="React Dashboard", description="Build react dashboards",
                                  metadata={"ultron": {"categories": ["web-frontend"]}})
        self.db.save_skill(meta, front)
        results, total = self.db.search_skills_by_text(q="react")
        self.assertGreater(total, 0)
        self.assertTrue(any(r["name"] == "React Dashboard" for r in results))


class TestClusterMixin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = _make_db(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_and_get_cluster(self):
        self.db.save_cluster("cid1", "topic A", centroid=[0.1, 0.2])
        c = self.db.get_cluster("cid1")
        self.assertIsNotNone(c)
        self.assertEqual(c["topic"], "topic A")

    def test_get_cluster_missing(self):
        self.assertIsNone(self.db.get_cluster("nonexistent"))

    def test_add_and_get_cluster_members(self):
        self.db.save_cluster("cid1", "t", centroid=[0.1])
        self.db.add_cluster_member("cid1", "m1")
        self.db.add_cluster_member("cid1", "m2")
        members = self.db.get_cluster_member_ids("cid1")
        self.assertIn("m1", members)
        self.assertIn("m2", members)

    def test_add_cluster_member_idempotent(self):
        self.db.save_cluster("cid1", "t", centroid=[0.1])
        self.db.add_cluster_member("cid1", "m1")
        self.db.add_cluster_member("cid1", "m1")
        members = self.db.get_cluster_member_ids("cid1")
        self.assertEqual(len(members), 1)

    def test_get_cluster_for_memory(self):
        self.db.save_cluster("cid1", "t", centroid=[0.1])
        self.db.add_cluster_member("cid1", "m1")
        cid = self.db.get_cluster_for_memory("m1")
        self.assertEqual(cid, "cid1")
        self.assertIsNone(self.db.get_cluster_for_memory("nonexistent"))

    def test_update_cluster_skill(self):
        self.db.save_cluster("cid1", "t", centroid=[0.1])
        ok = self.db.update_cluster_skill("cid1", "my-skill")
        self.assertTrue(ok)
        c = self.db.get_cluster("cid1")
        self.assertEqual(c["skill_slug"], "my-skill")

    def test_update_cluster_topic(self):
        self.db.save_cluster("cid1", "", centroid=[0.1])
        self.db.update_cluster_topic("cid1", "new topic")
        c = self.db.get_cluster("cid1")
        self.assertEqual(c["topic"], "new topic")

    def test_get_all_clusters(self):
        self.db.save_cluster("c1", "t1", centroid=[0.1])
        self.db.save_cluster("c2", "t2", centroid=[0.2])
        clusters = self.db.get_all_clusters()
        self.assertEqual(len(clusters), 2)

    def test_get_all_clusters_includes_member_ids_without_n_plus_one(self):
        self.db.save_cluster("c1", "t", centroid=[0.1])
        self.db.add_cluster_member("c1", "m1")
        self.db.add_cluster_member("c1", "m2")
        clusters = self.db.get_all_clusters()
        self.assertEqual(len(clusters[0]["memory_ids"]), 2)

    def test_get_cluster_dicts_ready_for_crystallization(self):
        self.db.save_cluster("c1", "t", centroid=[0.1])
        for i in range(3):
            self.db.add_cluster_member("c1", f"m{i}")
        ready = self.db.get_cluster_dicts_ready_for_crystallization(3)
        self.assertEqual(len(ready), 1)
        self.assertEqual(len(ready[0]["memory_ids"]), 3)
        self.db.update_cluster_skill("c1", "s")
        self.assertEqual(len(self.db.get_cluster_dicts_ready_for_crystallization(3)), 0)

    def test_count_cluster_members_since_no_evolution(self):
        self.db.save_cluster("cid1", "t", centroid=[0.1])
        self.db.add_cluster_member("cid1", "m1")
        self.db.add_cluster_member("cid1", "m2")
        count = self.db.count_cluster_members_since("cid1", "some-skill")
        self.assertEqual(count, 2)

    def test_count_cluster_members_since_uses_skill_slug_in_evolution(self):
        self.db.save_cluster("cid1", "t", centroid=[0.1])
        self.db.add_cluster_member("cid1", "m1")
        self.db.add_cluster_member("cid1", "m2")
        self.db.save_evolution_record(
            skill_slug="my-skill",
            cluster_id="cid1",
            old_version=None,
            new_version="1.0.0",
            old_score=None,
            new_score=0.8,
            status="crystallized",
            trigger="t",
            memory_count=2,
        )
        self.db.add_cluster_member("cid1", "m3")
        # SQLite CURRENT_TIMESTAMP is second-resolution; bump m3 so added_at > evolution ts.
        with self.db._get_connection() as conn:
            conn.execute(
                """UPDATE cluster_members SET added_at = datetime('now', '+10 seconds')
                   WHERE cluster_id = ? AND memory_id = ?""",
                ("cid1", "m3"),
            )
        count = self.db.count_cluster_members_since("cid1", "my-skill")
        self.assertEqual(count, 1)

    def test_save_evolution_record(self):
        self.db.save_cluster("cid1", "t", centroid=[0.1])
        eid = self.db.save_evolution_record(
            skill_slug="s", cluster_id="cid1",
            old_version=None, new_version="1.0.0",
            old_score=None, new_score=0.8,
            status="crystallized", trigger="background",
            memory_count=5,
        )
        self.assertIsNotNone(eid)


class TestDatabaseWipe(unittest.TestCase):
    def test_wipe_empty_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            stats = db.wipe_all_data()
            self.assertIsInstance(stats, dict)

    def test_wipe_with_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = _make_db(tmp)
            m = _make_memory("m1")
            db.save_memory_record(m)
            meta = SkillMeta(owner_id="o", slug="s", version="1.0.0", published_at=0)
            front = SkillFrontmatter(name="S", description="d", metadata={})
            db.save_skill(meta, front)
            stats = db.wipe_all_data()
            self.assertIsInstance(stats, dict)
            # memory_records and skills are wiped
            self.assertIsNone(db.get_memory_record("m1"))
            self.assertIsNone(db.get_skill("s"))


if __name__ == "__main__":
    unittest.main()
