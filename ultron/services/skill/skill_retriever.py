# Copyright (c) ModelScope Contributors. All rights reserved.
from dataclasses import dataclass
from typing import List, Optional

from ...core.models import (
    Skill,
    SkillMeta,
    SkillFrontmatter,
)
from ...core.database import Database
from ...core.embeddings import EmbeddingService
from ...utils.intent_analyzer import IntentAnalyzer
from ...core.logging import log_event


@dataclass
class RetrievalQuery:
    """Skill search request (natural language)."""
    query_text: str
    limit: Optional[int] = None


@dataclass
class RetrievalResult:
    """One ranked skill from semantic search."""
    skill: Skill
    similarity_score: float
    combined_score: float
    source: str = "internal"
    full_name: Optional[str] = None

    def to_dict(self) -> dict:
        d = {
            "slug": self.skill.meta.slug,
            "version": self.skill.meta.version,
            "name": self.skill.name,
            "description": self.skill.description,
            "similarity_score": round(self.similarity_score, 4),
            "combined_score": round(self.combined_score, 4),
            "source": self.source,
        }
        if self.full_name:
            d["full_name"] = self.full_name
        return d


class SkillRetriever:
    """
    Embed query text (optionally expanded via IntentAnalyzer), score all skills by
    cosine similarity, and return the top ``limit`` rows.
    """

    def __init__(
        self,
        database: Database,
        embedding_service: EmbeddingService,
        memory_service=None,
        config=None,
        llm_service=None,
    ):
        self.db = database
        self.embedding = embedding_service
        self.memory_service = memory_service
        self.config = config
        self.intent_analyzer = IntentAnalyzer(llm_service=llm_service)

    def search_skills(self, query: RetrievalQuery) -> List[RetrievalResult]:
        """Semantic search across internal skills and catalog; honors ``config.enable_intent_analysis``."""
        default_skill = (
            self.config.skill_search_default_limit if self.config else 5
        )
        limit = (
            default_skill if query.limit is None else max(1, query.limit)
        )
        enable_intent = self.config and self.config.enable_intent_analysis
        if enable_intent:
            queries = self.intent_analyzer.analyze(query.query_text)
        else:
            queries = [query.query_text]

        query_embeddings = [self.embedding.embed_text(q) for q in queries]

        results = []

        # Internal skills
        for skill_dict, embedding in self.db.get_skills_with_embeddings():
            best_sim = max(
                (self.embedding.cosine_similarity(q, embedding) for q in query_embeddings),
                default=0.0,
            )
            skill = self._dict_to_skill(skill_dict)
            results.append(RetrievalResult(
                skill=skill,
                similarity_score=max(0, best_sim),
                combined_score=max(0, best_sim),
                source="internal",
            ))

        # Catalog skills
        for cat_dict, embedding in self.db.get_catalog_skills_with_embeddings():
            best_sim = max(
                (self.embedding.cosine_similarity(q, embedding) for q in query_embeddings),
                default=0.0,
            )
            skill = self._catalog_dict_to_skill(cat_dict)
            results.append(RetrievalResult(
                skill=skill,
                similarity_score=max(0, best_sim),
                combined_score=max(0, best_sim),
                source="catalog",
                full_name=cat_dict.get("full_name"),
            ))

        results.sort(key=lambda x: x.combined_score, reverse=True)

        total = len(results)
        results = results[:limit]
        log_event(
            f"Skill search done: {len(results)}/{total}",
            action="search_skills",
            query=query.query_text[:60], count=len(results),
            detail=f"queries={len(queries)}",
        )
        return results

    def _dict_to_skill(self, skill_dict: dict) -> Skill:
        """Hydrate a lightweight ``Skill`` from DB metadata (no body or scripts)."""
        meta = SkillMeta(
            owner_id=skill_dict.get("owner_id", ""),
            slug=skill_dict.get("slug", ""),
            version=skill_dict.get("version", "1.0.0"),
            published_at=skill_dict.get("published_at", 0),
            parent_version=skill_dict.get("parent_version"),
            embedding=skill_dict.get("embedding"),
        )

        frontmatter = SkillFrontmatter(
            name=skill_dict.get("name", ""),
            description=skill_dict.get("description", ""),
            metadata={
                "ultron": {
                    "categories": skill_dict.get("categories", []),
                    "complexity": skill_dict.get("complexity", "medium"),
                    "source_type": skill_dict.get("source_type", ""),
                }
            }
        )

        return Skill(
            meta=meta,
            frontmatter=frontmatter,
            content="",
            scripts={},
            local_path=skill_dict.get("local_path"),
        )

    def _catalog_dict_to_skill(self, cat_dict: dict) -> Skill:
        """Build a lightweight Skill from a catalog_skills row."""
        meta = SkillMeta(
            owner_id=cat_dict.get("owner", ""),
            slug=cat_dict.get("name", ""),
            version="1.0.0",
            published_at=0,
        )
        frontmatter = SkillFrontmatter(
            name=cat_dict.get("display_name") or cat_dict.get("name", ""),
            description=cat_dict.get("description_en") or cat_dict.get("description", ""),
            metadata={
                "ultron": {
                    "categories": [cat_dict.get("category_id", "general")],
                    "source_type": "catalog",
                }
            },
        )
        return Skill(meta=meta, frontmatter=frontmatter, content="", scripts={})

    def search_with_memory_context(
        self,
        query: str,
        limit: Optional[int] = None,
    ) -> List[RetrievalResult]:
        """
        Run skill search, then bump scores for skills linked from memories that match ``query``.
        """
        default_skill = (
            self.config.skill_search_default_limit if self.config else 5
        )
        eff_limit = default_skill if limit is None else max(1, limit)
        if not self.memory_service:
            return self.search_skills(
                RetrievalQuery(query_text=query, limit=eff_limit),
            )

        retrieval_query = RetrievalQuery(
            query_text=query,
            limit=eff_limit * 2,
        )
        results = self.search_skills(retrieval_query)

        memory_results = self.memory_service.search_memories(query, limit=None)
        memory_skill_slugs = set()
        for mr in memory_results:
            if mr.record.generated_skill_slug:
                memory_skill_slugs.add(mr.record.generated_skill_slug)

        for result in results:
            if result.skill.meta.slug in memory_skill_slugs:
                result.combined_score *= 1.15

        results.sort(key=lambda x: x.combined_score, reverse=True)
        return results[:eff_limit]
