# Copyright (c) ModelScope Contributors. All rights reserved.
import logging
import re
from datetime import datetime
from typing import List, Optional

from ...config import UltronConfig, default_config
from ...core.database import Database
from ...core.embeddings import EmbeddingService
from ...core.models import (
    KnowledgeCluster,
    MemoryRecord,
    Skill,
    SkillFrontmatter,
    SkillMeta,
    SkillStatus,
)
from ...core.storage import SkillStorage
from ...utils.skill_parser import SkillParser
from .skill_cluster import KnowledgeClusterService
from .skill_catalog import SkillCatalogService

logger = logging.getLogger(__name__)


class SkillEvolutionEngine:
    """
    Crystallizes skills from knowledge clusters and re-crystallizes them
    as new memories flow in. Implements quality gates, faithfulness
    verification, and ratchet mechanism.
    """

    def __init__(
        self,
        database: Database,
        storage: SkillStorage,
        embedding_service: EmbeddingService,
        cluster_service: KnowledgeClusterService,
        config: Optional[UltronConfig] = None,
        llm_orchestrator=None,
        catalog: Optional[SkillCatalogService] = None,
    ):
        self.db = database
        self.storage = storage
        self.embedding = embedding_service
        self.cluster_service = cluster_service
        self.config = config or default_config
        self.llm_orchestrator = llm_orchestrator
        self.catalog = catalog
        self.parser = SkillParser()

    # ── Public API ──

    def crystallize_cluster(
        self,
        cluster: KnowledgeCluster,
        trigger: str = "new_memory",
    ) -> Optional[Skill]:
        """Crystallize a skill from a knowledge cluster that has reached critical mass."""
        memories = self.cluster_service.get_cluster_memories(cluster.cluster_id)
        if len(memories) < self.config.crystallization_threshold:
            return None

        memory_dicts = [m.to_dict(include_embedding=False) for m in memories]

        # Generate topic if missing
        if not cluster.topic and self.llm_orchestrator:
            topic = self.llm_orchestrator.generate_cluster_topic(memory_dicts)
            if topic:
                self.db.update_cluster_topic(cluster.cluster_id, topic)
                cluster.topic = topic

        # LLM crystallization
        result = self._llm_crystallize(memory_dicts, cluster.topic)
        if not result or result.get("quality") == "insufficient":
            logger.info("Cluster %s: LLM deemed insufficient for crystallization", cluster.cluster_id[:8])
            return None

        content = result.get("content", "")

        # Quality gate
        if not self._meets_quality_bar(content):
            logger.info("Cluster %s: failed quality bar", cluster.cluster_id[:8])
            return None

        # Faithfulness verification
        verification = self._verify(content, memory_dicts, is_recrystallization=False)
        if not self._verification_passed(verification):
            logger.info("Cluster %s: failed verification (grounded=%.2f)",
                        cluster.cluster_id[:8],
                        (verification or {}).get("grounded_in_evidence", 0))
            return None

        structure_score = self._compute_structure_score(verification)

        # Build and save skill
        skill = self._build_and_save_skill(
            name=result["name"],
            description=result["description"],
            content=content,
            cluster=cluster,
            structure_score=structure_score,
        )
        if not skill:
            return None

        # Update cluster
        self.db.update_cluster_skill(cluster.cluster_id, skill.meta.slug)

        # Archive superseded 1:1 skills
        for old_slug in cluster.superseded_slugs:
            self.db.update_skill_status(old_slug, "1.0.0", SkillStatus.ARCHIVED)

        # Log evolution record
        self.db.save_evolution_record(
            skill_slug=skill.meta.slug,
            cluster_id=cluster.cluster_id,
            old_version=None,
            new_version=skill.meta.version,
            old_score=None,
            new_score=structure_score,
            status="crystallized",
            trigger=trigger,
            memory_count=len(memories),
            new_memory_ids=[m.id for m in memories],
            superseded_skills=cluster.superseded_slugs,
            mutation_summary=f"Crystallized from {len(memories)} memories",
        )

        logger.info("Crystallized skill '%s' from cluster %s (%d memories, score=%.2f)",
                     skill.meta.slug, cluster.cluster_id[:8], len(memories), structure_score)
        return skill

    def recrystallize_skill(
        self,
        cluster: KnowledgeCluster,
        trigger: str = "new_memory",
    ) -> Optional[Skill]:
        """Re-crystallize an existing skill with new knowledge from its cluster."""
        if not cluster.skill_slug:
            return None

        old_skill_dict = self.db.get_skill(cluster.skill_slug)
        if not old_skill_dict:
            return None

        old_skill = self.storage.load_skill(
            old_skill_dict["slug"], old_skill_dict["version"],
        )
        if not old_skill:
            return None

        memories = self.cluster_service.get_cluster_memories(cluster.cluster_id)
        memory_dicts = [m.to_dict(include_embedding=False) for m in memories]
        new_count = self.db.count_cluster_members_since(
            cluster.cluster_id, cluster.skill_slug,
        )

        # LLM re-crystallization
        current_content = old_skill.content
        result = self._llm_recrystallize(
            current_content, old_skill.meta.version, memory_dicts, new_count,
        )
        if not result or result.get("evolution") == "unnecessary":
            logger.info("Skill '%s': LLM deemed re-crystallization unnecessary", cluster.skill_slug)
            return None

        new_content = result.get("content", "")

        # Quality gate
        if not self._meets_quality_bar(new_content):
            logger.info("Skill '%s': re-crystallized version failed quality bar", cluster.skill_slug)
            return None

        # Faithfulness verification
        verification = self._verify(new_content, memory_dicts, is_recrystallization=True)
        if not self._verification_passed(verification):
            self.db.save_evolution_record(
                skill_slug=cluster.skill_slug,
                cluster_id=cluster.cluster_id,
                old_version=old_skill.meta.version,
                new_version="",
                old_score=old_skill.meta.structure_score,
                new_score=0,
                status="constraint_failed",
                trigger=trigger,
                memory_count=len(memories),
                mutation_summary="Failed faithfulness verification",
            )
            return None

        new_structure_score = self._compute_structure_score(verification)
        old_structure_score = old_skill.meta.structure_score or 0.0

        # Ratchet gate: new must be better
        if new_structure_score <= old_structure_score:
            self.db.save_evolution_record(
                skill_slug=cluster.skill_slug,
                cluster_id=cluster.cluster_id,
                old_version=old_skill.meta.version,
                new_version="",
                old_score=old_structure_score,
                new_score=new_structure_score,
                status="revert",
                trigger=trigger,
                memory_count=len(memories),
                mutation_summary=f"Ratchet: {new_structure_score:.2f} <= {old_structure_score:.2f}",
            )
            logger.info("Skill '%s': ratchet rejected (%.2f <= %.2f)",
                        cluster.skill_slug, new_structure_score, old_structure_score)
            return None

        # Build new version
        new_version = self._increment_version(old_skill.meta.version)
        new_skill = self._build_and_save_skill(
            name=result.get("name") or old_skill.name,
            description=result.get("description") or old_skill.description,
            content=new_content,
            cluster=cluster,
            structure_score=new_structure_score,
            version=new_version,
            parent_version=old_skill.meta.version,
            evolution_count=old_skill.meta.evolution_count + 1,
        )
        if not new_skill:
            return None

        self.db.update_cluster_skill(cluster.cluster_id, new_skill.meta.slug)

        self.db.save_evolution_record(
            skill_slug=new_skill.meta.slug,
            cluster_id=cluster.cluster_id,
            old_version=old_skill.meta.version,
            new_version=new_version,
            old_score=old_structure_score,
            new_score=new_structure_score,
            status="recrystallized",
            trigger=trigger,
            memory_count=len(memories),
            new_memory_ids=[m.id for m in memories[-new_count:]] if new_count > 0 else [],
            mutation_summary=f"Re-crystallized with {new_count} new memories",
        )

        logger.info("Re-crystallized skill '%s' v%s → v%s (score %.2f → %.2f)",
                     new_skill.meta.slug, old_skill.meta.version, new_version,
                     old_structure_score, new_structure_score)
        return new_skill

    def run_evolution_cycle(self, limit: Optional[int] = None) -> dict:
        """Run one evolution cycle: crystallize ready clusters + re-crystallize updated ones."""
        if not self.config.evolution_enabled:
            return {"skipped": True, "reason": "evolution_disabled"}

        eff_limit = limit or self.config.evolution_batch_limit
        crystallized = 0
        recrystallized = 0

        # Phase 1: crystallize clusters that reached critical mass
        for cluster in self.cluster_service.get_clusters_ready_to_crystallize()[:eff_limit]:
            result = self.crystallize_cluster(cluster, trigger="background")
            if result:
                crystallized += 1

        remaining = eff_limit - crystallized
        if remaining <= 0:
            return {"crystallized": crystallized, "recrystallized": 0}

        # Phase 2: re-crystallize clusters with enough new memories
        for cluster in self.cluster_service.get_clusters_ready_to_recrystallize()[:remaining]:
            result = self.recrystallize_skill(cluster, trigger="background")
            if result:
                recrystallized += 1

        summary = {"crystallized": crystallized, "recrystallized": recrystallized}
        if crystallized or recrystallized:
            logger.info("Evolution cycle: %s", summary)
        return summary

    # ── Internal ──

    def _llm_crystallize(self, memories: List[dict], topic: str) -> Optional[dict]:
        if not self.llm_orchestrator:
            return None
        try:
            return self.llm_orchestrator.crystallize_skill_from_cluster(memories, topic)
        except Exception as e:
            logger.warning("LLM crystallization failed: %s", e)
            return None

    def _llm_recrystallize(
        self, current_content: str, version: str, memories: List[dict], new_count: int,
    ) -> Optional[dict]:
        if not self.llm_orchestrator:
            return None
        try:
            return self.llm_orchestrator.recrystallize_skill(
                current_content, version, memories, new_count,
            )
        except Exception as e:
            logger.warning("LLM re-crystallization failed: %s", e)
            return None

    def _verify(
        self, content: str, memories: List[dict], is_recrystallization: bool,
    ) -> Optional[dict]:
        if not self.llm_orchestrator:
            return None
        try:
            return self.llm_orchestrator.verify_skill(content, memories, is_recrystallization)
        except Exception as e:
            logger.warning("LLM verification failed: %s", e)
            return None

    @staticmethod
    def _verification_passed(verification: Optional[dict]) -> bool:
        if not verification:
            return True  # No LLM available, skip verification
        grounded = verification.get("grounded_in_evidence", 0)
        if isinstance(grounded, (int, float)) and grounded < 0.8:
            return False
        if verification.get("has_contradiction"):
            return False
        return True

    @staticmethod
    def _compute_structure_score(verification: Optional[dict]) -> float:
        if not verification:
            return 0.5  # Default when no LLM
        clarity = float(verification.get("workflow_clarity", 0.5))
        specificity = float(verification.get("specificity_and_reusability", 0.5))
        preserves = float(verification.get("preserves_existing_value", 1.0))
        return 0.35 * clarity + 0.35 * specificity + 0.30 * preserves

    @staticmethod
    def _meets_quality_bar(content: str) -> bool:
        if len(content) < 500:
            return False
        checks = 0
        # Has multiple steps (numbered or bulleted)
        step_patterns = re.findall(r'(?:^|\n)\s*(?:\d+[\.\)]\s|[-*]\s|#{1,3}\s)', content)
        if len(step_patterns) >= 3:
            checks += 1
        # Has trigger conditions
        trigger_keywords = ["when", "trigger", "use this", "适用", "触发", "何时", "场景"]
        if any(kw in content.lower() for kw in trigger_keywords):
            checks += 1
        # Has edge case handling
        edge_keywords = ["error", "fail", "exception", "fallback", "if not", "otherwise",
                         "异常", "失败", "回退", "边界", "注意"]
        if any(kw in content.lower() for kw in edge_keywords):
            checks += 1
        # Sufficient length
        if len(content) >= 800:
            checks += 1
        return checks >= 3

    def _build_and_save_skill(
        self,
        name: str,
        description: str,
        content: str,
        cluster: KnowledgeCluster,
        structure_score: float,
        version: str = "1.0.0",
        parent_version: Optional[str] = None,
        evolution_count: int = 0,
    ) -> Optional[Skill]:
        try:
            slug = self._slugify(name) or f"cluster-{cluster.cluster_id[:8]}"

            categories = ["general"]
            if self.catalog:
                categories = self.catalog.suggest_categories(
                    content, description, name=name,
                ) or ["general"]

            metadata = {
                "openclaw": {"emoji": "🧬"},
                "ultron": {
                    "source_type": "cluster_crystallization",
                    "categories": categories,
                    "complexity": "medium",
                    "cluster_id": cluster.cluster_id,
                },
            }
            skill_md = self.parser.build_skill_md(
                name=name, description=description,
                content=content, metadata=metadata,
            )
            frontmatter, parsed_content = self.parser.parse_skill_md(skill_md)
            if not frontmatter:
                return None

            meta = SkillMeta(
                owner_id="ultron-evolution",
                slug=slug,
                version=version,
                published_at=int(datetime.now().timestamp() * 1000),
                parent_version=parent_version,
                status=SkillStatus.ACTIVE,
                cluster_id=cluster.cluster_id,
                evolution_count=evolution_count,
                structure_score=structure_score,
            )
            skill = Skill(
                meta=meta, frontmatter=frontmatter,
                content=parsed_content, scripts={},
            )
            meta.embedding = self.embedding.embed_skill(name, description, content)

            local_path = self.storage.save_skill(skill)
            skill.local_path = local_path
            self.db.save_skill(meta, frontmatter, local_path)
            return skill
        except Exception as e:
            logger.warning("Failed to build/save evolved skill: %s", e)
            return None

    @staticmethod
    def _slugify(text: str) -> str:
        slug = text.lower()
        slug = re.sub(r'[^a-z0-9\u4e00-\u9fff]+', '-', slug)
        return slug.strip('-')[:50] or ''

    @staticmethod
    def _increment_version(version: str) -> str:
        try:
            parts = version.split('.')
            parts[1] = str(int(parts[1]) + 1)
            return '.'.join(parts)
        except Exception:
            return "1.1.0"
