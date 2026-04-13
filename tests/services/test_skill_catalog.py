# Copyright (c) ModelScope Contributors. All rights reserved.
import tempfile
import unittest
from pathlib import Path
from ultron.core.database import Database
from ultron.services.skill.skill_catalog import CategoryInfo, SkillCatalogService


class _UnavailableLLM:
    is_available = False


class TestCategoryInfo(unittest.TestCase):
    def test_to_dict(self):
        c = CategoryInfo(name="n", description="d", skill_count=3)
        self.assertEqual(c.to_dict()["skill_count"], 3)


class TestSkillCatalogService(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.tmp.name) / "c.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_suggest_categories_keywords_react(self):
        svc = SkillCatalogService(self.db, llm_service=_UnavailableLLM())
        cats = svc.suggest_categories("Building a react dashboard component", "")
        self.assertIn("web-frontend", cats)

    def test_get_category_tree(self):
        svc = SkillCatalogService(self.db, llm_service=_UnavailableLLM())
        tree = svc.get_category_tree()
        self.assertIn("development_engineering", tree)

    def test_classifiable_slugs_excludes_source_only(self):
        svc = SkillCatalogService(self.db, llm_service=_UnavailableLLM())
        slugs = svc.classifiable_slugs()
        self.assertNotIn("error_learning", slugs)


if __name__ == "__main__":
    unittest.main()
