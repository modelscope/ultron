# Copyright (c) ModelScope Contributors. All rights reserved.
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from ultron.config import UltronConfig
from ultron.core.database import Database
from ultron.core.models import KnowledgeCluster, MemoryRecord
from ultron.services.skill.skill_cluster import KnowledgeClusterService


def _make_memory(mid: str, embedding=None) -> MemoryRecord:
    now = datetime.now()
    m = MemoryRecord(
        id=mid,
        memory_type="pattern",
        content=f"content {mid}",
        context="",
        resolution="",
        tier="hot",
        hit_count=1,
        status="active",
        created_at=now,
        last_hit_at=now,
    )
    m.embedding = embedding or [1.0, 0.0]
    return m


class TestKnowledgeClusterServiceAssign(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self.tmp.name, "test.db"))
        cfg = UltronConfig()
        cfg.cluster_similarity_threshold = 0.75
        cfg.crystallization_threshold = 3
        cfg.recrystallization_delta = 2
        self.emb = MagicMock()
        self.svc = KnowledgeClusterService(self.db, self.emb, config=cfg)

    def tearDown(self):
        self.tmp.cleanup()

    def test_assign_no_embedding_returns_none(self):
        m = _make_memory("m1", embedding=None)
        m.embedding = None
        result = self.svc.assign_memory_to_cluster(m)
        self.assertIsNone(result)

    def test_assign_creates_new_cluster_when_no_clusters(self):
        self.emb.cosine_similarity.return_value = 0.0
        m = _make_memory("m1")
        cluster_id = self.svc.assign_memory_to_cluster(m)
        self.assertIsNotNone(cluster_id)
        clusters = self.db.get_all_clusters()
        self.assertEqual(len(clusters), 1)

    def test_assign_joins_existing_cluster_above_threshold(self):
        self.emb.cosine_similarity.return_value = 0.9
        m1 = _make_memory("m1")
        c1 = self.svc.assign_memory_to_cluster(m1)

        m2 = _make_memory("m2")
        c2 = self.svc.assign_memory_to_cluster(m2)
        self.assertEqual(c1, c2)
        self.assertEqual(len(self.db.get_all_clusters()), 1)

    def test_assign_creates_new_cluster_below_threshold(self):
        self.emb.cosine_similarity.return_value = 0.5
        m1 = _make_memory("m1")
        self.svc.assign_memory_to_cluster(m1)

        m2 = _make_memory("m2")
        self.svc.assign_memory_to_cluster(m2)
        self.assertEqual(len(self.db.get_all_clusters()), 2)

    def test_assign_idempotent_already_assigned(self):
        self.emb.cosine_similarity.return_value = 0.0
        m = _make_memory("m1")
        c1 = self.svc.assign_memory_to_cluster(m)
        c2 = self.svc.assign_memory_to_cluster(m)
        self.assertEqual(c1, c2)
        self.assertEqual(len(self.db.get_all_clusters()), 1)


class TestKnowledgeClusterServiceReadiness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self.tmp.name, "test.db"))
        cfg = UltronConfig()
        cfg.cluster_similarity_threshold = 0.75
        cfg.crystallization_threshold = 3
        cfg.recrystallization_delta = 2
        self.emb = MagicMock()
        self.emb.cosine_similarity.return_value = 0.0
        self.svc = KnowledgeClusterService(self.db, self.emb, config=cfg)

    def tearDown(self):
        self.tmp.cleanup()

    def _fill_cluster(self, n: int) -> str:
        """Create n memories in a single cluster and return cluster_id."""
        memories = [_make_memory(f"m{i}") for i in range(n)]
        cluster_id = None
        for idx, m in enumerate(memories):
            # First memory creates a new cluster; subsequent ones join it
            self.emb.cosine_similarity.return_value = 0.0 if idx == 0 else 0.9
            cluster_id = self.svc.assign_memory_to_cluster(m)
        return cluster_id

    def test_get_clusters_ready_to_crystallize_below_threshold(self):
        self._fill_cluster(2)
        ready = self.svc.get_clusters_ready_to_crystallize()
        self.assertEqual(len(ready), 0)

    def test_get_clusters_ready_to_crystallize_at_threshold(self):
        self._fill_cluster(3)
        ready = self.svc.get_clusters_ready_to_crystallize()
        self.assertEqual(len(ready), 1)

    def test_get_clusters_ready_to_crystallize_skips_crystallized(self):
        cluster_id = self._fill_cluster(3)
        self.db.update_cluster_skill(cluster_id, "some-skill")
        ready = self.svc.get_clusters_ready_to_crystallize()
        self.assertEqual(len(ready), 0)

    def test_get_clusters_ready_to_recrystallize_not_crystallized(self):
        self._fill_cluster(5)
        ready = self.svc.get_clusters_ready_to_recrystallize()
        self.assertEqual(len(ready), 0)

    def test_get_clusters_ready_to_recrystallize_enough_new(self):
        cluster_id = self._fill_cluster(3)
        self.db.update_cluster_skill(cluster_id, "skill-a")
        # Add 2 more memories after crystallization
        for i in range(10, 12):
            m = _make_memory(f"m{i}")
            self.emb.cosine_similarity.return_value = 0.9
            self.svc.assign_memory_to_cluster(m)
        ready = self.svc.get_clusters_ready_to_recrystallize()
        self.assertEqual(len(ready), 1)


class TestKnowledgeClusterServiceGetMemories(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self.tmp.name, "test.db"))
        cfg = UltronConfig()
        cfg.cluster_similarity_threshold = 0.75
        self.emb = MagicMock()
        self.emb.cosine_similarity.return_value = 0.0
        self.svc = KnowledgeClusterService(self.db, self.emb, config=cfg)

    def tearDown(self):
        self.tmp.cleanup()

    def test_get_cluster_memories_returns_records(self):
        now = datetime.now()
        # Insert memory directly into DB
        from ultron.core.models import MemoryRecord
        m = _make_memory("mem-abc")
        self.db.save_memory_record(m)
        cluster_id = self.svc.assign_memory_to_cluster(m)
        memories = self.svc.get_cluster_memories(cluster_id)
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].id, "mem-abc")

    def test_get_cluster_memories_empty_cluster(self):
        self.db.save_cluster("cid-x", "", [0.5, 0.5])
        memories = self.svc.get_cluster_memories("cid-x")
        self.assertEqual(memories, [])


class TestKnowledgeClusterServiceInitialClustering(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self.tmp.name, "test.db"))
        cfg = UltronConfig()
        cfg.cluster_similarity_threshold = 0.75
        self.emb = MagicMock()
        self.svc = KnowledgeClusterService(self.db, self.emb, config=cfg)

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_initial_clustering_no_memories(self):
        self.db.get_memory_records_with_embeddings = MagicMock(return_value=[])
        summary = self.svc.run_initial_clustering()
        self.assertEqual(summary["memories_processed"], 0)
        self.assertEqual(summary["total_clusters"], 0)

    def test_run_initial_clustering_skips_already_assigned(self):
        m = _make_memory("m1")
        self.db.save_memory_record(m)
        self.emb.cosine_similarity.return_value = 0.0
        # First pass
        self.svc.assign_memory_to_cluster(m)
        # Second pass via run_initial_clustering should skip
        import pickle
        raw = pickle.dumps(m.embedding)
        self.db.get_memory_records_with_embeddings = MagicMock(
            return_value=[(m.to_dict(), m.embedding)]
        )
        summary = self.svc.run_initial_clustering()
        self.assertEqual(summary["memories_processed"], 0)


if __name__ == "__main__":
    unittest.main()
