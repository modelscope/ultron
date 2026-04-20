# Copyright (c) ModelScope Contributors. All rights reserved.
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from ultron.core.database import Database
from ultron.services.skill.skill_catalog import CategoryInfo, SkillCatalogService


class _UnavailableLLM:
    is_available = False


class _AvailableLLM:
    is_available = True

    def dashscope_user_messages(self, prompt):
        return [{"role": "user", "content": prompt}]

    def call(self, messages):
        return '["web-frontend"]'

    def parse_json_response(self, resp, expect_array=False):
        import json
        return json.loads(resp)


class TestCategoryInfo(unittest.TestCase):
    def test_to_dict(self):
        c = CategoryInfo(name="n", description="d", skill_count=3)
        self.assertEqual(c.to_dict()["skill_count"], 3)

    def test_to_dict_all_fields(self):
        c = CategoryInfo(name="web-frontend", description="Web dev", skill_count=10)
        d = c.to_dict()
        self.assertEqual(d["name"], "web-frontend")
        self.assertEqual(d["description"], "Web dev")


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
        self.assertNotIn("evolution", slugs)
        self.assertNotIn("catalog", slugs)

    def test_suggest_categories_fallback_to_general(self):
        svc = SkillCatalogService(self.db, llm_service=_UnavailableLLM())
        cats = svc.suggest_categories("zzz completely unrelated content xyz", "")
        self.assertIn("general", cats)

    def test_suggest_categories_llm_path(self):
        svc = SkillCatalogService(self.db, llm_service=_AvailableLLM())
        cats = svc.suggest_categories("react component", "frontend")
        self.assertIn("web-frontend", cats)

    def test_suggest_categories_llm_invalid_slug_filtered(self):
        class BadLLM:
            is_available = True
            def dashscope_user_messages(self, p): return []
            def call(self, m): return '["nonexistent-slug"]'
            def parse_json_response(self, r, expect_array=False):
                import json; return json.loads(r)

        svc = SkillCatalogService(self.db, llm_service=BadLLM())
        cats = svc.suggest_categories("content", "desc")
        # Falls back to keyword
        self.assertIsInstance(cats, list)

    def test_get_all_categories_returns_list(self):
        svc = SkillCatalogService(self.db, llm_service=_UnavailableLLM())
        cats = svc.get_all_categories()
        self.assertGreater(len(cats), 0)
        self.assertTrue(all(hasattr(c, "name") for c in cats))

    def test_get_category_statistics(self):
        svc = SkillCatalogService(self.db, llm_service=_UnavailableLLM())
        stats = svc.get_category_statistics()
        self.assertIn("total_skills", stats)
        self.assertIn("dimension_stats", stats)
        self.assertIn("top_categories", stats)

    def test_suggest_categories_devops_keywords(self):
        svc = SkillCatalogService(self.db, llm_service=_UnavailableLLM())
        cats = svc.suggest_categories("deploy with docker and kubernetes", "")
        self.assertIn("devops-cloud", cats)

    def test_suggest_categories_multiple_matches_capped_at_3(self):
        svc = SkillCatalogService(self.db, llm_service=_UnavailableLLM())
        cats = svc.suggest_categories(
            "react docker git bash python pandas llm", ""
        )
        self.assertLessEqual(len(cats), 3)


if __name__ == "__main__":
    unittest.main()

