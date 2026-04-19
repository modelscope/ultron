# Copyright (c) ModelScope Contributors. All rights reserved.
import logging
import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from ...config import UltronConfig, default_config
from ...core.database import Database
from ...core.embeddings import EmbeddingService
from ...core.models import KnowledgeCluster, MemoryRecord

logger = logging.getLogger(__name__)


class KnowledgeClusterService:
    """
    Manages knowledge clusters — groups of semantically related memories
    that serve as raw material for skill crystallization.
    """

    def __init__(
        self,
        database: Database,
        embedding_service: EmbeddingService,
        config: Optional[UltronConfig] = None,
    ):
        self.db = database
        self.embedding = embedding_service
        self.config = config or default_config

    @property
    def similarity_threshold(self) -> float:
        return getattr(self.config, "cluster_similarity_threshold", 0.75)

    @property
    def crystallization_threshold(self) -> int:
        return getattr(self.config, "crystallization_threshold", 5)

    @property
    def recrystallization_delta(self) -> int:
        return getattr(self.config, "recrystallization_delta", 3)

    def assign_memory_to_cluster(self, memory: MemoryRecord) -> Optional[str]:
        """Assign a memory to the best matching cluster, or create a new one.

        Returns the cluster_id the memory was assigned to, or None if
        the memory has no embedding.
        """
        if not memory.embedding:
            return None

        # Check if already assigned
        existing = self.db.get_cluster_for_memory(memory.id)
        if existing:
            return existing

        # Find best matching cluster
        best_cluster_id = None
        best_similarity = 0.0

        for cluster_dict, centroid in self.db.get_clusters_with_centroids():
            sim = self.embedding.cosine_similarity(memory.embedding, centroid)
            if sim > best_similarity:
                best_similarity = sim
                best_cluster_id = cluster_dict["cluster_id"]

        if best_cluster_id and best_similarity >= self.similarity_threshold:
            self.db.add_cluster_member(best_cluster_id, memory.id)
            self._update_centroid(best_cluster_id)
            logger.info(
                "Memory %s assigned to cluster %s (sim=%.3f)",
                memory.id[:8], best_cluster_id[:8], best_similarity,
            )
            return best_cluster_id

        # Create new cluster
        cluster_id = str(uuid.uuid4())
        self.db.save_cluster(
            cluster_id=cluster_id,
            topic="",  # Will be set by LLM later
            centroid=memory.embedding,
        )
        self.db.add_cluster_member(cluster_id, memory.id)
        logger.info("Created new cluster %s for memory %s", cluster_id[:8], memory.id[:8])
        return cluster_id

    def get_clusters_ready_to_crystallize(self) -> List[KnowledgeCluster]:
        """Find clusters that have reached critical mass but have no skill yet."""
        cluster_dicts = self.db.get_cluster_dicts_ready_for_crystallization(
            self.crystallization_threshold,
        )
        return [KnowledgeCluster.from_dict(d) for d in cluster_dicts]

    def get_clusters_ready_to_recrystallize(self) -> List[KnowledgeCluster]:
        """Find clusters with enough new memories since last crystallization."""
        ready = []
        for cluster_dict in self.db.get_all_clusters():
            cluster = KnowledgeCluster.from_dict(cluster_dict)
            if not cluster.skill_slug:
                continue  # Not yet crystallized
            new_count = self.db.count_cluster_members_since(
                cluster.cluster_id, cluster.skill_slug,
            )
            if new_count >= self.recrystallization_delta:
                ready.append(cluster)
        return ready

    def get_cluster_memories(self, cluster_id: str) -> List[MemoryRecord]:
        """Load all memories belonging to a cluster."""
        memory_ids = self.db.get_cluster_member_ids(cluster_id)
        memories = []
        for mid in memory_ids:
            record = self.db.get_memory_record(mid)
            if record:
                memories.append(MemoryRecord.from_dict(record))
        return memories

    def run_initial_clustering(self) -> dict:
        """One-time clustering of all existing memories with embeddings.

        Scans all active memories, assigns each to a cluster.
        Returns summary stats.
        """
        all_memories = self.db.get_memory_records_with_embeddings()
        assigned = 0
        new_clusters = 0
        existing_clusters = 0

        for memory_dict, embedding in all_memories:
            memory = MemoryRecord.from_dict(memory_dict)
            memory.embedding = embedding

            existing = self.db.get_cluster_for_memory(memory.id)
            if existing:
                continue

            before_count = len(self.db.get_all_clusters())
            self.assign_memory_to_cluster(memory)
            after_count = len(self.db.get_all_clusters())

            assigned += 1
            if after_count > before_count:
                new_clusters += 1
            else:
                existing_clusters += 1

        clusters = self.db.get_all_clusters()
        summary = {
            "memories_processed": assigned,
            "new_clusters_created": new_clusters,
            "assigned_to_existing": existing_clusters,
            "total_clusters": len(clusters),
            "clusters_ready_to_crystallize": len(self.get_clusters_ready_to_crystallize()),
        }
        logger.info("Initial clustering done: %s", summary)
        return summary

    def _update_centroid(self, cluster_id: str) -> None:
        """Recompute cluster centroid as mean of member embeddings."""
        member_ids = self.db.get_cluster_member_ids(cluster_id)
        if not member_ids:
            return

        embeddings = []
        for record in self.db.get_memory_records_by_ids(member_ids):
            emb = record.get("embedding")
            if isinstance(emb, list) and emb:
                embeddings.append(emb)

        if not embeddings:
            return

        dim = len(embeddings[0])
        centroid = [0.0] * dim
        for emb in embeddings:
            for i in range(min(dim, len(emb))):
                centroid[i] += emb[i]
        n = len(embeddings)
        centroid = [x / n for x in centroid]

        self.db.update_cluster_centroid(cluster_id, centroid)
