# Copyright (c) ModelScope Contributors. All rights reserved.
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class SkillStatus(Enum):
    """Lifecycle state of a published skill."""
    ACTIVE = "active"
    DEGRADED = "degraded"
    PENDING_REVIEW = "pending_review"
    ARCHIVED = "archived"


class SourceType(Enum):
    """How the skill was produced or curated."""
    ERROR_LEARNING = "error_learning"
    SECURITY_LEARNING = "security_learning"
    GENERATION = "generation"


class Complexity(Enum):
    """Declared difficulty for executors."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class MemoryTier(Enum):
    """Retention and retrieval priority for shared memories."""
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


class MemoryType(Enum):
    """Content category (technical, safety, and general-assistant life tips)."""
    ERROR = "error"
    SECURITY = "security"
    CORRECTION = "correction"
    PATTERN = "pattern"
    PREFERENCE = "preference"
    LIFE = "life"


class MemoryStatus(Enum):
    """Memory lifecycle: active while in use, archived before TTL deletion."""
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass
class SkillMeta:
    """
    On-disk companion to ``_meta.json`` for a skill package.
    """
    owner_id: str
    slug: str
    version: str
    published_at: int
    parent_version: Optional[str] = None
    embedding: Optional[List[float]] = None
    status: SkillStatus = SkillStatus.ACTIVE
    cluster_id: Optional[str] = None
    evolution_count: int = 0
    structure_score: Optional[float] = None

    def to_dict(self) -> dict:
        """Serialize for JSON APIs and storage."""
        return {
            "ownerId": self.owner_id,
            "slug": self.slug,
            "version": self.version,
            "publishedAt": self.published_at,
            "parentVersion": self.parent_version,
            "embedding": self.embedding,
            "status": self.status.value if isinstance(self.status, SkillStatus) else self.status,
            "clusterId": self.cluster_id,
            "evolutionCount": self.evolution_count,
            "structureScore": self.structure_score,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SkillMeta":
        status = data.get("status", "active")
        if isinstance(status, str):
            status = SkillStatus(status)
        return cls(
            owner_id=data.get("ownerId", ""),
            slug=data.get("slug", ""),
            version=data.get("version", "1.0.0"),
            published_at=data.get("publishedAt", 0),
            parent_version=data.get("parentVersion"),
            embedding=data.get("embedding"),
            status=status,
            cluster_id=data.get("clusterId"),
            evolution_count=data.get("evolutionCount", 0),
            structure_score=data.get("structureScore"),
        )

    def to_json(self) -> str:
        """Pretty-printed JSON for ``_meta.json``."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ============ Evolution models ============


@dataclass
class KnowledgeCluster:
    """A group of semantically related memories — the raw material for skill crystallization."""
    cluster_id: str
    topic: str
    memory_ids: List[str] = field(default_factory=list)
    centroid: List[float] = field(default_factory=list)
    skill_slug: Optional[str] = None
    superseded_slugs: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    last_updated_at: Optional[datetime] = None

    @property
    def size(self) -> int:
        return len(self.memory_ids)

    def to_dict(self) -> dict:
        return {
            "cluster_id": self.cluster_id,
            "topic": self.topic,
            "memory_ids": self.memory_ids,
            "skill_slug": self.skill_slug,
            "superseded_slugs": self.superseded_slugs,
            "size": self.size,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_updated_at": self.last_updated_at.isoformat() if self.last_updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeCluster":
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        last_updated_at = data.get("last_updated_at")
        if isinstance(last_updated_at, str):
            last_updated_at = datetime.fromisoformat(last_updated_at)
        memory_ids = data.get("memory_ids", [])
        if isinstance(memory_ids, str):
            try:
                memory_ids = json.loads(memory_ids)
            except (json.JSONDecodeError, TypeError):
                memory_ids = []
        superseded = data.get("superseded_slugs", [])
        if isinstance(superseded, str):
            try:
                superseded = json.loads(superseded)
            except (json.JSONDecodeError, TypeError):
                superseded = []
        return cls(
            cluster_id=data.get("cluster_id", ""),
            topic=data.get("topic", ""),
            memory_ids=memory_ids,
            centroid=data.get("centroid", []),
            skill_slug=data.get("skill_slug"),
            superseded_slugs=superseded,
            created_at=created_at,
            last_updated_at=last_updated_at,
        )


@dataclass
class EvolutionRecord:
    """One evolution attempt — crystallization, re-crystallization, or revert."""
    id: str
    skill_slug: str
    cluster_id: str
    timestamp: datetime
    old_version: Optional[str]
    new_version: str
    old_score: Optional[float]
    new_score: float
    status: str              # "crystallized" | "recrystallized" | "revert" | "constraint_failed"
    trigger: str             # "initial_clustering" | "new_memory" | "manual"
    memory_count: int
    new_memory_ids: List[str] = field(default_factory=list)
    superseded_skills: List[str] = field(default_factory=list)
    mutation_summary: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "skill_slug": self.skill_slug,
            "cluster_id": self.cluster_id,
            "timestamp": self.timestamp.isoformat(),
            "old_version": self.old_version,
            "new_version": self.new_version,
            "old_score": self.old_score,
            "new_score": self.new_score,
            "status": self.status,
            "trigger": self.trigger,
            "memory_count": self.memory_count,
            "new_memory_ids": self.new_memory_ids,
            "superseded_skills": self.superseded_skills,
            "mutation_summary": self.mutation_summary,
        }


@dataclass
class SkillFrontmatter:
    """YAML front matter parsed from ``SKILL.md``."""
    name: str
    description: str
    metadata: dict = field(default_factory=dict)

    @property
    def ultron_metadata(self) -> dict:
        return self.metadata.get("ultron", {})

    @property
    def openclaw_metadata(self) -> dict:
        return self.metadata.get("openclaw", {})

    @property
    def categories(self) -> List[str]:
        return self.ultron_metadata.get("categories", [])

    @property
    def complexity(self) -> str:
        return self.ultron_metadata.get("complexity", "medium")

    @property
    def source_type(self) -> str:
        return self.ultron_metadata.get("source_type", "generation")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SkillFrontmatter":
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Skill:
    """Parsed skill: meta + frontmatter + markdown body + optional script blobs."""
    meta: SkillMeta
    frontmatter: SkillFrontmatter
    content: str
    scripts: Dict[str, str] = field(default_factory=dict)
    local_path: Optional[str] = None

    @property
    def full_id(self) -> str:
        return f"{self.meta.slug}-{self.meta.version}"

    @property
    def name(self) -> str:
        return self.frontmatter.name

    @property
    def description(self) -> str:
        return self.frontmatter.description

    @property
    def categories(self) -> List[str]:
        return self.frontmatter.categories

    @property
    def complexity(self) -> str:
        return self.frontmatter.complexity


@dataclass
class SkillUsageRecord:
    """One invocation of a skill by an agent."""
    id: str
    skill_slug: str
    skill_version: str
    task_id: str
    success: bool
    used_at: datetime
    execution_time: Optional[float] = None
    feedback: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "skill_slug": self.skill_slug,
            "skill_version": self.skill_version,
            "task_id": self.task_id,
            "success": self.success,
            "used_at": self.used_at.isoformat(),
            "execution_time": self.execution_time,
            "feedback": self.feedback,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SkillUsageRecord":
        used_at = data.get("used_at")
        if isinstance(used_at, str):
            used_at = datetime.fromisoformat(used_at)
        elif used_at is None:
            used_at = datetime.now()

        return cls(
            id=data.get("id", ""),
            skill_slug=data.get("skill_slug", ""),
            skill_version=data.get("skill_version", ""),
            task_id=data.get("task_id", ""),
            success=data.get("success", False),
            used_at=used_at,
            execution_time=data.get("execution_time"),
            feedback=data.get("feedback"),
        )



# ============ Memory models ============


@dataclass
class MemoryRecord:
    """
    Shared remote memory row (also maps to local mirror fields where used).
    """
    id: str
    memory_type: str
    content: str
    context: str
    resolution: str
    tier: str
    hit_count: int
    status: str
    created_at: datetime
    last_hit_at: datetime
    embedding: List[float] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    generated_skill_slug: Optional[str] = None
    summary_l0: str = ""
    overview_l1: str = ""

    def to_dict(self, *, include_embedding: bool = True) -> dict:
        d = {
            "id": self.id,
            "memory_type": self.memory_type,
            "content": self.content,
            "context": self.context,
            "resolution": self.resolution,
            "tier": self.tier,
            "hit_count": self.hit_count,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "last_hit_at": self.last_hit_at.isoformat(),
            "tags": self.tags,
            "generated_skill_slug": self.generated_skill_slug,
            "summary_l0": self.summary_l0,
            "overview_l1": self.overview_l1,
        }
        if include_embedding:
            d["embedding"] = self.embedding
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryRecord":
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now()

        last_hit_at = data.get("last_hit_at")
        if isinstance(last_hit_at, str):
            last_hit_at = datetime.fromisoformat(last_hit_at)
        elif last_hit_at is None:
            last_hit_at = created_at

        tags = data.get("tags", [])
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = []

        return cls(
            id=data.get("id", ""),
            memory_type=data.get("memory_type", "error"),
            content=data.get("content", ""),
            context=data.get("context", ""),
            resolution=data.get("resolution", ""),
            tier=data.get("tier", "warm"),
            hit_count=data.get("hit_count", 1),
            status=data.get("status", "active"),
            created_at=created_at,
            last_hit_at=last_hit_at,
            embedding=data.get("embedding", []),
            tags=tags,
            generated_skill_slug=data.get("generated_skill_slug"),
            summary_l0=data.get("summary_l0", ""),
            overview_l1=data.get("overview_l1", ""),
        )


# ============ Harness models ============


class HarnessVisibility(Enum):
    """Share visibility level for harness profiles."""
    LINK = "link"
    PUBLIC = "public"
    PRIVATE = "private"


@dataclass
class HarnessDevice:
    """Registered agent (terminal) for a user in the HarnessHub."""
    user_id: str
    agent_id: str
    display_name: str = ""
    created_at: Optional[datetime] = None
    last_sync_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "userId": self.user_id,
            "agentId": self.agent_id,
            "displayName": self.display_name,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "lastSyncAt": self.last_sync_at.isoformat() if self.last_sync_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HarnessDevice":
        created_at = data.get("createdAt") or data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        last_sync_at = data.get("lastSyncAt") or data.get("last_sync_at")
        if isinstance(last_sync_at, str):
            last_sync_at = datetime.fromisoformat(last_sync_at)
        return cls(
            user_id=data.get("userId") or data.get("user_id", ""),
            agent_id=data.get("agentId") or data.get("agent_id", ""),
            display_name=data.get("displayName") or data.get("display_name", ""),
            created_at=created_at,
            last_sync_at=last_sync_at,
        )


@dataclass
class HarnessProfile:
    """Per-(user, agent) workspace profile stored on the server."""
    user_id: str
    agent_id: str
    revision: int = 1
    resources_json: str = "{}"
    product: str = "nanobot"
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "userId": self.user_id,
            "agentId": self.agent_id,
            "revision": self.revision,
            "resources": json.loads(self.resources_json),
            "product": self.product,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HarnessProfile":
        resources = data.get("resources") or data.get("resources_json", "{}")
        if isinstance(resources, dict):
            resources = json.dumps(resources, ensure_ascii=False)
        updated_at = data.get("updatedAt") or data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        return cls(
            user_id=data.get("userId") or data.get("user_id", ""),
            agent_id=data.get("agentId") or data.get("agent_id", ""),
            revision=data.get("revision", 1),
            resources_json=resources,
            product=data.get("product", "nanobot"),
            updated_at=updated_at,
        )


@dataclass
class HarnessShare:
    """Share token linking to a snapshot of a user's agent profile."""
    token: str
    source_user_id: str
    source_agent_id: str
    visibility: str = "link"
    snapshot_json: str = "{}"
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "token": self.token,
            "sourceUserId": self.source_user_id,
            "sourceDeviceId": self.source_agent_id,
            "visibility": self.visibility,
            "snapshot": json.loads(self.snapshot_json),
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HarnessShare":
        snapshot = data.get("snapshot") or data.get("snapshot_json", "{}")
        if isinstance(snapshot, dict):
            snapshot = json.dumps(snapshot, ensure_ascii=False)
        created_at = data.get("createdAt") or data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        return cls(
            token=data.get("token", ""),
            source_user_id=data.get("sourceUserId") or data.get("source_user_id", ""),
            source_agent_id=data.get("sourceDeviceId") or data.get("source_agent_id", ""),
            visibility=data.get("visibility", "link"),
            snapshot_json=snapshot,
            created_at=created_at,
        )
