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


class TestSkillRetrieverSearch(unittest.TestCase):
    def test_search_merges_internal_and_catalog(self):
        db = MagicMock()
        db.get_skills_with_embeddings.return_value = [
            ({
                "slug": "a",
                "version": "1.0.0",
                "owner_id": "o",
                "published_at": 0,
                "name": "A",
                "description": "",
                "categories": [],
                "complexity": "low",
            }, [1.0, 0.0]),
        ]
        db.get_catalog_skills_with_embeddings.return_value = []

        emb = MagicMock()
        emb.embed_text.return_value = [1.0, 0.0]
        emb.cosine_similarity.return_value = 0.9

        cfg = UltronConfig()
        cfg.enable_intent_analysis = False

        r = SkillRetriever(db, emb, config=cfg, llm_service=None)
        out = r.search_skills(RetrievalQuery(query_text="q", limit=5))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].skill.meta.slug, "a")
        self.assertEqual(out[0].source, "internal")

    def test_dict_to_skill_categories(self):
        db = MagicMock()
        emb = MagicMock()
        ret = SkillRetriever(db, emb, config=UltronConfig(), llm_service=None)
        sk = ret._dict_to_skill({
            "slug": "z",
            "version": "2.0.0",
            "owner_id": "u",
            "published_at": 1,
            "name": "Zed",
            "description": "dz",
            "categories": ["web-frontend"],
            "complexity": "high",
        })
        self.assertEqual(sk.meta.slug, "z")
        self.assertEqual(sk.frontmatter.categories, ["web-frontend"])
        self.assertEqual(sk.frontmatter.complexity, "high")


if __name__ == "__main__":
    unittest.main()
