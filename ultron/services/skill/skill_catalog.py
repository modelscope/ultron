# Copyright (c) ModelScope Contributors. All rights reserved.
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from ...core.database import Database
from ...core.llm_service import LLMService
from ...config import UltronConfig, default_config
from .taxonomy import (
    CATEGORY_DEFINITIONS,
    CATEGORY_TREE,
    KEYWORD_MAP,
    SOURCE_ONLY_SLUGS,
)

logger = logging.getLogger(__name__)

_MAX_CONTENT_EXCERPT_CHARS = 8_000


@dataclass
class CategoryInfo:
    """One taxonomy row with optional live skill count."""
    name: str
    description: str
    skill_count: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "skill_count": self.skill_count,
        }


class SkillCatalogService:
    """
    ClawHub-style category taxonomy in SQLite. ``suggest_categories`` prefers
    an LLM (default ``qwen3.6-flash`` via config) and falls back to keyword hits.
    """

    def __init__(
        self,
        database: Database,
        config: Optional[UltronConfig] = None,
        llm_service: Optional[LLMService] = None,
    ):
        self.db = database
        self.config = config or default_config
        if llm_service is not None:
            self._llm = llm_service
        else:
            cap = min(self.config.llm_max_input_tokens, 32_768)
            self._llm = LLMService(
                provider=self.config.llm_provider,
                model=self.config.skill_category_llm_model,
                base_url=self.config.llm_base_url,
                api_key=self.config.llm_api_key,
                max_input_tokens=cap,
                prompt_reserve_tokens=self.config.llm_prompt_reserve_tokens,
                tiktoken_encoding=self.config.llm_token_count_encoding,
                request_timeout_seconds=self.config.llm_request_timeout_seconds,
                max_retries=self.config.llm_max_retries,
                retry_base_delay_seconds=self.config.llm_retry_base_delay_seconds,
            )
        self._init_categories()

    def _init_categories(self) -> None:
        """Upsert built-in category rows."""
        for name, description in CATEGORY_DEFINITIONS.items():
            self.db.save_category(name, description)

    def get_all_categories(self) -> List[CategoryInfo]:
        """All categories with active skill counts, sorted by count descending."""
        categories = self.db.get_all_categories()
        skills = self.db.get_all_skills(status="active", limit=10000)

        skill_counts = {}
        for skill in skills:
            for cat in skill.get("categories", []):
                skill_counts[cat] = skill_counts.get(cat, 0) + 1

        results = []
        for cat in categories:
            name = cat["name"]
            results.append(CategoryInfo(
                name=name,
                description=cat.get("description", ""),
                skill_count=skill_counts.get(name, 0),
            ))

        results.sort(key=lambda x: x.skill_count, reverse=True)
        return results

    def get_category_tree(self) -> Dict[str, List[str]]:
        """High-level dimensions mapped to category slugs (for rollup stats)."""
        return CATEGORY_TREE

    def classifiable_slugs(self) -> List[str]:
        """Taxonomy slugs that may be assigned by LLM or keywords (excludes source-type labels)."""
        return sorted(
            k for k in CATEGORY_DEFINITIONS
            if k not in SOURCE_ONLY_SLUGS
        )

    def suggest_categories(
        self,
        content: str,
        description: str = "",
        *,
        name: str = "",
    ) -> List[str]:
        """
        Return 1-3 category slugs. Uses DashScope when ``self._llm.is_available``;
        otherwise uses keyword scoring over ``content`` and ``description``.
        """
        if self._llm.is_available:
            llm_result = self._suggest_categories_llm(content, description, name=name)
            if llm_result:
                return llm_result

        return self._suggest_categories_keywords(content, description)

    def _allowed_slug_set(self) -> frozenset:
        return frozenset(self.classifiable_slugs())

    def _suggest_categories_llm(
        self,
        content: str,
        description: str,
        *,
        name: str,
    ) -> Optional[List[str]]:
        allowed = self._allowed_slug_set()
        lines = [
            f"- {slug}: {CATEGORY_DEFINITIONS[slug]}"
            for slug in self.classifiable_slugs()
        ]
        allowed_block = "\n".join(lines)
        excerpt = (content or "")[:_MAX_CONTENT_EXCERPT_CHARS]
        prompt = f"""You assign Ultron skill taxonomy labels.

Each label must be exactly one slug from the list below (copy slug text verbatim).

{allowed_block}

Output rules:
- Return ONLY a JSON array of 1–3 strings, e.g. ["web-frontend","devops-cloud"]
- Every element must appear in the slug list above
- Use ["general"] when the skill does not clearly fit any specific slug

Skill name: {name or "(none)"}
Description: {description or "(none)"}
Content excerpt:
{excerpt}
"""
        try:
            resp = self._llm.call(self._llm.dashscope_user_messages(prompt))
            if not resp:
                return None
            parsed = self._llm.parse_json_response(resp, expect_array=True)
            if not isinstance(parsed, list) or not parsed:
                return None
            out = []
            seen = set()
            for item in parsed:
                slug = str(item).strip()
                if slug in allowed and slug not in seen:
                    seen.add(slug)
                    out.append(slug)
                if len(out) >= 3:
                    break
            if not out:
                return None
            return out
        except Exception as exc:
            logger.warning("Skill category LLM failed, using keyword fallback: %s", exc)
            return None

    def _suggest_categories_keywords(
        self,
        content: str,
        description: str,
    ) -> List[str]:
        text = f"{content} {description}".lower()
        scores = {}

        for category, keywords in KEYWORD_MAP.items():
            if category == "general":
                continue
            hit_count = sum(1 for kw in keywords if kw in text)
            if hit_count > 0:
                scores[category] = hit_count

        sorted_cats = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        suggested = [cat for cat, _ in sorted_cats[:3]]

        if not suggested:
            suggested.append("general")

        return suggested

    def get_category_statistics(self) -> Dict:
        """Aggregate counts for stats APIs."""
        categories = self.get_all_categories()

        total_skills = sum(cat.skill_count for cat in categories)
        categories_with_skills = sum(1 for cat in categories if cat.skill_count > 0)

        tree = self.get_category_tree()
        dimension_stats = {}
        for dimension, cats in tree.items():
            cat_dict = {c.name: c.skill_count for c in categories}
            dimension_stats[dimension] = sum(cat_dict.get(c, 0) for c in cats)

        return {
            "total_skills": total_skills,
            "total_categories": len(categories),
            "categories_with_skills": categories_with_skills,
            "dimension_stats": dimension_stats,
            "top_categories": [
                {"name": cat.name, "count": cat.skill_count}
                for cat in categories[:10]
            ],
        }
