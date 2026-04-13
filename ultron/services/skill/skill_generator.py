# Copyright (c) ModelScope Contributors. All rights reserved.
import logging
import math
import re
from datetime import datetime
from typing import List, Optional

from ...config import UltronConfig, default_config
from ...core.models import (
    Skill,
    SkillMeta,
    SkillStatus,
    MemoryRecord,
)
from ...core.database import Database
from ...core.storage import SkillStorage
from ...core.embeddings import EmbeddingService
from ...utils.skill_parser import SkillParser
from .skill_catalog import SkillCatalogService


logger = logging.getLogger(__name__)


class SkillGeneratorService:
    """
    Crystallize high-value memories into reusable skills.
    Uses LLM to synthesize abstracted skill documents when available,
    falls back to template-based generation otherwise.
    """

    def __init__(
        self,
        database: Database,
        storage: SkillStorage,
        embedding_service: EmbeddingService,
        parser: Optional[SkillParser] = None,
        config: Optional[UltronConfig] = None,
        llm_orchestrator=None,
        catalog: Optional[SkillCatalogService] = None,
    ):
        self.db = database
        self.storage = storage
        self.embedding = embedding_service
        self.parser = parser or SkillParser()
        self.config = config or default_config
        self.llm_orchestrator = llm_orchestrator
        self.catalog = catalog

    def generate_skill_from_memory(
        self,
        memory_id: str,
    ) -> Optional[Skill]:
        """
        Generate a skill from a HOT memory.

        1. Load memory
        2. Dedup against existing skills
        3. Gather related memories + contributions
        4. Build skill (LLM first, template fallback)
        5. Save
        """
        memory_dict = self.db.get_memory_record(memory_id)
        if not memory_dict:
            return None

        memory = MemoryRecord.from_dict(memory_dict)

        dup = self._find_duplicate_skill(memory)
        if dup:
            self.db.update_memory_generated_skill(memory_id, dup)
            return None

        related = self._find_related_memories(memory, limit=5)
        contributions = self.db.get_memory_contributions(memory_id)
        skill = self._build_skill_from_memories(memory, related, contributions)
        if skill:
            self.db.update_memory_generated_skill(memory_id, skill.meta.slug)
        return skill

    def auto_detect_and_generate(self, limit: Optional[int] = None) -> List[Skill]:
        """
        Scan memory store for skill-worthy candidates, scored and ranked.

        Score = hit_count + hotness * 3
        Only HOT memories without an existing skill are considered.

        When ``limit`` is omitted, uses ``config.skill_auto_detect_batch_limit`` (``ULTRON_SKILL_AUTO_DETECT_LIMIT``).
        """
        eff_limit = (
            self.config.skill_auto_detect_batch_limit
            if limit is None
            else max(1, limit)
        )
        candidates = self.db.get_promotion_candidates()
        scored = []
        for m in candidates:
            hotness = self._calculate_hotness(m.get("last_hit_at"))
            score = (
                m.get("hit_count", 1)
                + hotness * 3
            )
            scored.append((m, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        generated: List[Skill] = []
        for memory_dict, _ in scored[:eff_limit]:
            memory = MemoryRecord.from_dict(memory_dict)
            dup = self._find_duplicate_skill(memory)
            if dup:
                self.db.update_memory_generated_skill(memory.id, dup)
                continue

            related = self._find_related_memories(memory, limit=3)
            contributions = self.db.get_memory_contributions(memory.id)
            skill = self._build_skill_from_memories(
                memory, related, contributions,
            )
            if skill:
                self.db.update_memory_generated_skill(memory.id, skill.meta.slug)
                generated.append(skill)

        return generated

    def suggest_skill_improvements(self, skill_slug: str) -> List[dict]:
        """Find memories that could improve an existing skill."""
        skill_dict = self.db.get_skill(skill_slug)
        if not skill_dict or not skill_dict.get("embedding"):
            return []

        skill_embedding = skill_dict["embedding"]
        suggestions = []
        for memory_dict, embedding in self.db.get_memory_records_with_embeddings():
            if memory_dict.get("generated_skill_slug") == skill_slug:
                continue
            sim = self.embedding.cosine_similarity(skill_embedding, embedding)
            if sim > 0.6:
                suggestions.append({
                    "memory_id": memory_dict.get("id"),
                    "memory_type": memory_dict.get("memory_type"),
                    "content_preview": memory_dict.get("content", "")[:200],
                    "hit_count": memory_dict.get("hit_count", 1),
                    "similarity": round(sim, 4),
                })

        suggestions.sort(key=lambda x: x["similarity"], reverse=True)
        return suggestions[:10]

    # ============ Internal ============

    def _build_skill_from_memories(
        self,
        primary: MemoryRecord,
        related: List[MemoryRecord],
        contributions: List[dict],
    ) -> Optional[Skill]:
        """Build a skill from memories. LLM synthesis first, template fallback."""
        try:
            # Try LLM synthesis
            llm_result = self._llm_generate(primary, related, contributions)
            if llm_result:
                name = llm_result["name"]
                description = llm_result["description"]
                full_content = llm_result["content"]
            else:
                name, description, full_content = self._template_generate(
                    primary, related, contributions)

            slug = self._slugify(name) or self._slugify(primary.content[:30])
            version = "1.0.0"
            existing = self.db.get_skill(slug)
            if existing:
                version = self._increment_version(existing.get("version", "1.0.0"))

            if self.catalog:
                bundle = "\n".join(
                    x for x in (
                        full_content,
                        description,
                        primary.content,
                        primary.context,
                        primary.resolution,
                    )
                    if x
                )
                categories = self.catalog.suggest_categories(
                    bundle, description, name=name,
                )
            else:
                categories = list(primary.tags) if primary.tags else []
                if not categories:
                    categories = ["general"]
            if primary.memory_type == "error":
                categories = list(dict.fromkeys(categories + ["debugging"]))
            elif primary.memory_type == "security":
                categories = list(dict.fromkeys(categories + ["security-passwords"]))
            if not categories:
                categories = ["general"]

            metadata = {
                "openclaw": {"emoji": "🧠"},
                "ultron": {
                    "source_type": "memory_crystallization",
                    "categories": categories,
                    "complexity": "medium",
                    "source_memory_id": primary.id,
                },
            }
            skill_md = self.parser.build_skill_md(
                name=name, description=description,
                content=full_content, metadata=metadata,
            )
            frontmatter, parsed_content = self.parser.parse_skill_md(skill_md)
            if not frontmatter:
                return None

            meta = SkillMeta(
                owner_id="ultron-system",
                slug=slug,
                version=version,
                published_at=int(datetime.now().timestamp() * 1000),
                status=SkillStatus.ACTIVE,
            )
            skill = Skill(
                meta=meta, frontmatter=frontmatter,
                content=parsed_content, scripts={},
            )
            meta.embedding = self.embedding.embed_skill(name, description, full_content)

            local_path = self.storage.save_skill(skill)
            skill.local_path = local_path
            self.db.save_skill(meta, frontmatter, local_path)
            return skill

        except Exception as e:
            logger.warning("Failed to generate skill from memory: %s", e)
            return None

    def _llm_generate(
        self,
        primary: MemoryRecord,
        related: List[MemoryRecord],
        contributions: List[dict],
    ) -> Optional[dict]:
        """Try LLM-based skill synthesis. Returns {"name", "description", "content"} or None."""
        if not self.llm_orchestrator:
            return None
        try:
            return self.llm_orchestrator.generate_skill_content(
                primary_content=primary.content,
                primary_context=primary.context,
                primary_resolution=primary.resolution,
                related_memories=[m.to_dict() for m in related],
                contributions=contributions,
            )
        except Exception:
            return None

    def _template_generate(
        self,
        primary: MemoryRecord,
        related: List[MemoryRecord],
        contributions: List[dict],
    ) -> tuple:
        """Template-based fallback when LLM is unavailable."""
        if primary.memory_type == "error":
            name = f"fix-{self._slugify(primary.content[:30])}"
            description = f"Fix for {primary.memory_type} pattern"
        elif primary.memory_type == "security":
            name = f"sec-{self._slugify(primary.content[:30])}"
            description = f"Security incident response pattern"
        else:
            name = f"pattern-{self._slugify(primary.content[:30])}"
            description = f"Pattern from {primary.hit_count} experiences"

        parts = [f"# {description}\n", f"## Problem\n\n{primary.content}\n"]
        if primary.context:
            parts.append(f"## Context\n\n{primary.context}\n")
        if primary.resolution:
            parts.append(f"## Solution\n\n{primary.resolution}\n")

        if contributions:
            parts.append(f"## Alternative Solutions ({len(contributions)} agents)\n")
            for i, c in enumerate(contributions, 1):
                if c.get("resolution"):
                    parts.append(f"{i}. {c['resolution'][:300]}\n")

        if related:
            parts.append("## Related Experiences\n")
            for i, r in enumerate(related, 1):
                parts.append(f"{i}. {r.content[:200]}\n")

        return name, description, "\n".join(parts)

    def _find_related_memories(self, target: MemoryRecord, limit: int = 5) -> List[MemoryRecord]:
        """Find semantically similar memories to enrich the skill."""
        if not target.embedding:
            return []
        results = []
        for memory_dict, embedding in self.db.get_memory_records_with_embeddings(
            memory_type=target.memory_type,
        ):
            if memory_dict.get("id") == target.id:
                continue
            sim = self.embedding.cosine_similarity(target.embedding, embedding)
            if sim > 0.5:
                results.append((MemoryRecord.from_dict(memory_dict), sim))
        results.sort(key=lambda x: x[1], reverse=True)
        return [r[0] for r in results[:limit]]

    def _find_duplicate_skill(self, memory: MemoryRecord, threshold: float = 0.80) -> Optional[str]:
        """Check if a semantically similar skill already exists."""
        if not memory.embedding:
            return None
        for skill_dict, skill_emb in (self.db.get_skills_with_embeddings() or []):
            if self.embedding.cosine_similarity(memory.embedding, skill_emb) > threshold:
                return skill_dict.get("slug")
        return None

    @staticmethod
    def _slugify(text: str) -> str:
        slug = text.lower()
        slug = re.sub(r'[^a-z0-9\u4e00-\u9fff]+', '-', slug)
        return slug.strip('-')[:50] or 'unknown'

    @staticmethod
    def _increment_version(version: str) -> str:
        try:
            parts = version.split('.')
            parts[-1] = str(int(parts[-1]) + 1)
            return '.'.join(parts)
        except Exception:
            return "1.0.1"

    @staticmethod
    def _calculate_hotness(last_hit_at) -> float:
        if not last_hit_at:
            return 0.0
        if isinstance(last_hit_at, str):
            try:
                last_hit_at = datetime.fromisoformat(last_hit_at)
            except (ValueError, TypeError):
                return 0.0
        days = max((datetime.now() - last_hit_at).total_seconds() / 86400.0, 0)
        return math.exp(-0.05 * days)
