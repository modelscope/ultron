# Copyright (c) ModelScope Contributors. All rights reserved.
import tempfile
import unittest
from pathlib import Path

from ultron.core.database import Database


class TestCatalogSkillMixin(unittest.TestCase):
    """
    Catalog skills table: bulk upsert, query by full_name, embeddings filter, and stats.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.tmp.name) / "test.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_bulk_upsert_and_query(self):
        skills = [
            {
                "full_name": "@ns/skill-a",
                "name": "skill-a",
                "display_name": "Skill A",
                "path": "@ns",
                "description": "描述A",
                "description_en": "Description A",
                "owner": "owner1",
                "category_id": "dev-tools",
                "category_name": "开发工具",
                "embedding": [0.1, 0.2, 0.3],
            },
            {
                "full_name": "@ns/skill-b",
                "name": "skill-b",
                "display_name": "Skill B",
                "path": "@ns",
                "description": "描述B",
                "description_en": "Description B",
                "owner": "owner2",
                "category_id": "ai-media",
                "category_name": "媒体处理",
                "embedding": [0.4, 0.5, 0.6],
            },
        ]
        count = self.db.bulk_upsert_catalog_skills(skills)
        self.assertEqual(count, 2)

        s = self.db.get_catalog_skill("@ns/skill-a")
        self.assertIsNotNone(s)
        self.assertEqual(s["display_name"], "Skill A")
        self.assertEqual(s["category_id"], "dev-tools")

        self.assertIsNone(self.db.get_catalog_skill("@ns/missing"))

    def test_get_catalog_skills_with_embeddings(self):
        skills = [
            {
                "full_name": "@ns/with-emb",
                "name": "with-emb",
                "embedding": [1.0, 0.0],
            },
            {
                "full_name": "@ns/no-emb",
                "name": "no-emb",
                "embedding": None,
            },
        ]
        self.db.bulk_upsert_catalog_skills(skills)
        results = self.db.get_catalog_skills_with_embeddings()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0]["full_name"], "@ns/with-emb")
        self.assertEqual(results[0][1], [1.0, 0.0])

    def test_upsert_is_idempotent(self):
        skill = {
            "full_name": "@ns/skill-x",
            "name": "skill-x",
            "description": "v1",
            "embedding": [1.0],
        }
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


class TestDatabaseWipe(unittest.TestCase):
    """
    Ensures wipe_all_data returns a dict without raising on an empty database.
    """

    def test_wipe_empty_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(str(Path(tmp) / "t.db"))
            stats = db.wipe_all_data()
            self.assertIsInstance(stats, dict)


if __name__ == "__main__":
    unittest.main()
