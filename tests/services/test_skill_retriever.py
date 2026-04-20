# Copyright (c) ModelScope Contributors. All rights reserved.
import unittest
from unittest.mock import MagicMock

from ultron.config import UltronConfig
from ultron.services.skill.skill_retriever import RetrievalQuery, RetrievalResult, SkillRetriever


class TestRetrievalResult(unittest.TestCase):
    def test_to_dict_round_scores(self):
        meta = MagicMock()
        meta.slug = "s"
        meta.version = "1.0.0"
        skill = MagicMock()
        skill.meta = meta
        skill.name = "N"
        skill.description = "D"
        rr = RetrievalResult(
            skill=skill,
            similarity_score=0.876543,
            combined_score=0.812345,
            full_name="@x/s",
        )
        d = rr.to_dict()
        self.assertEqual(d["similarity_score"], 0.8765)
        self.assertEqual(d["full_name"], "@x/s")

    def test_to_dict_no_full_name(self):
        meta = MagicMock()
        meta.slug = "s"
        meta.version = "1.0.0"
        skill = MagicMock()
        skill.meta = meta
        skill.name = "N"
        skill.description = "D"
        rr = RetrievalResult(skill=skill, similarity_score=0.5, combined_score=0.5)
        d = rr.to_dict()
        self.assertNotIn("full_name", d)

    def test_to_dict_source_default(self):
        meta = MagicMock()
        meta.slug = "s"
        meta.version = "1.0.0"
        skill = MagicMock()
        skill.meta = meta
        skill.name = "N"
        skill.description = "D"
        rr = RetrievalResult(skill=skill, similarity_score=0.5, combined_score=0.5)
        self.assertEqual(rr.to_dict()["source"], "internal")


class TestSkillRetrieverSearch(unittest.TestCase):
    def _make_retriever(self, internal=None, catalog=None, sim=0.9):
        db = MagicMock()
        db.get_skills_with_embeddings.return_value = internal or []
        db.get_catalog_skills_with_embeddings.return_value = catalog or []
        emb = MagicMock()
        emb.embed_text.return_value = [1.0, 0.0]
        emb.cosine_similarity.return_value = sim
        cfg = UltronConfig()
        cfg.enable_intent_analysis = False
        cfg.skill_search_default_limit = 5
        return SkillRetriever(db, emb, config=cfg, llm_service=None)

    def test_search_merges_internal_and_catalog(self):
        r = self._make_retriever(
            internal=[({
                "slug": "a", "version": "1.0.0", "owner_id": "o", "published_at": 0,
                "name": "A", "description": "", "categories": [], "complexity": "low",
            }, [1.0, 0.0])],
        )
        out = r.search_skills(RetrievalQuery(query_text="q", limit=5))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].skill.meta.slug, "a")
        self.assertEqual(out[0].source, "internal")

    def test_search_includes_catalog_results(self):
        r = self._make_retriever(
            catalog=[({
                "name": "cat-skill", "full_name": "@org/cat-skill",
                "display_name": "Cat Skill", "description": "d",
                "description_en": "d en", "category_id": "ai-llms",
                "owner": "org",
            }, [1.0, 0.0])],
        )
        out = r.search_skills(RetrievalQuery(query_text="q", limit=5))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].source, "catalog")
        self.assertEqual(out[0].full_name, "@org/cat-skill")

    def test_search_respects_limit(self):
        internal = [({
            "slug": f"s{i}", "version": "1.0.0", "owner_id": "o", "published_at": i,
            "name": f"S{i}", "description": "", "categories": [], "complexity": "low",
        }, [1.0, 0.0]) for i in range(10)]
        r = self._make_retriever(internal=internal)
        out = r.search_skills(RetrievalQuery(query_text="q", limit=3))
        self.assertEqual(len(out), 3)

    def test_search_uses_default_limit_when_none(self):
        internal = [({
            "slug": f"s{i}", "version": "1.0.0", "owner_id": "o", "published_at": i,
            "name": f"S{i}", "description": "", "categories": [], "complexity": "low",
        }, [1.0, 0.0]) for i in range(10)]
        r = self._make_retriever(internal=internal)
        out = r.search_skills(RetrievalQuery(query_text="q"))
        self.assertEqual(len(out), 5)  # default limit

    def test_search_sorts_by_combined_score_desc(self):
        db = MagicMock()
        db.get_skills_with_embeddings.return_value = [
            ({"slug": "low", "version": "1.0.0", "owner_id": "o", "published_at": 0,
              "name": "Low", "description": "", "categories": [], "complexity": "low"}, [0.0, 1.0]),
            ({"slug": "high", "version": "1.0.0", "owner_id": "o", "published_at": 0,
              "name": "High", "description": "", "categories": [], "complexity": "low"}, [1.0, 0.0]),
        ]
        db.get_catalog_skills_with_embeddings.return_value = []
        emb = MagicMock()
        emb.embed_text.return_value = [1.0, 0.0]
        emb.cosine_similarity.side_effect = lambda q, e: 0.9 if e == [1.0, 0.0] else 0.1
        cfg = UltronConfig()
        cfg.enable_intent_analysis = False
        cfg.skill_search_default_limit = 5
        r = SkillRetriever(db, emb, config=cfg, llm_service=None)
        out = r.search_skills(RetrievalQuery(query_text="q", limit=5))
        self.assertEqual(out[0].skill.meta.slug, "high")

    def test_dict_to_skill_categories(self):
        r = self._make_retriever()
        sk = r._dict_to_skill({
            "slug": "z", "version": "2.0.0", "owner_id": "u", "published_at": 1,
            "name": "Zed", "description": "dz", "categories": ["web-frontend"],
            "complexity": "high",
        })
        self.assertEqual(sk.meta.slug, "z")
        self.assertEqual(sk.frontmatter.categories, ["web-frontend"])
        self.assertEqual(sk.frontmatter.complexity, "high")

    def test_catalog_dict_to_skill(self):
        r = self._make_retriever()
        sk = r._catalog_dict_to_skill({
            "name": "my-skill", "full_name": "@org/my-skill",
            "display_name": "My Skill", "description": "zh desc",
            "description_en": "en desc", "category_id": "ai-llms", "owner": "org",
        })
        self.assertEqual(sk.meta.slug, "my-skill")
        self.assertEqual(sk.frontmatter.name, "My Skill")
        self.assertEqual(sk.frontmatter.description, "en desc")

    def test_search_with_memory_context_no_memory_service(self):
        r = self._make_retriever(
            internal=[({
                "slug": "a", "version": "1.0.0", "owner_id": "o", "published_at": 0,
                "name": "A", "description": "", "categories": [], "complexity": "low",
            }, [1.0, 0.0])],
        )
        out = r.search_with_memory_context("query", limit=5)
        self.assertEqual(len(out), 1)

    def test_search_with_memory_context_boosts_linked_skill(self):
        db = MagicMock()
        db.get_skills_with_embeddings.return_value = [
            ({"slug": "linked", "version": "1.0.0", "owner_id": "o", "published_at": 0,
              "name": "Linked", "description": "", "categories": [], "complexity": "low"}, [1.0, 0.0]),
        ]
        db.get_catalog_skills_with_embeddings.return_value = []
        emb = MagicMock()
        emb.embed_text.return_value = [1.0, 0.0]
        emb.cosine_similarity.return_value = 0.5
        cfg = UltronConfig()
        cfg.enable_intent_analysis = False
        cfg.skill_search_default_limit = 5
        mem_result = MagicMock()
        mem_result.record.generated_skill_slug = "linked"
        mem_svc = MagicMock()
        mem_svc.search_memories.return_value = [mem_result]
        r = SkillRetriever(db, emb, memory_service=mem_svc, config=cfg, llm_service=None)
        out = r.search_with_memory_context("query", limit=5)
        self.assertGreater(out[0].combined_score, 0.5)


if __name__ == "__main__":
    unittest.main()

