# Copyright (c) ModelScope Contributors. All rights reserved.
import json
import pickle
import sqlite3
import uuid
from collections import defaultdict
from datetime import datetime
from typing import List, Optional, Tuple


class _ClusterMixin:
    """Knowledge cluster and evolution record operations."""

    def _ensure_cluster_tables(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_clusters (
                    cluster_id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL DEFAULT '',
                    centroid BLOB,
                    skill_slug TEXT,
                    superseded_slugs TEXT DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cluster_members (
                    cluster_id TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (cluster_id, memory_id)
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_cluster_members_memory ON cluster_members(memory_id)"
            )
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS evolution_records (
                    id TEXT PRIMARY KEY,
                    skill_slug TEXT NOT NULL,
                    cluster_id TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    old_version TEXT,
                    new_version TEXT NOT NULL,
                    old_score REAL,
                    new_score REAL NOT NULL,
                    status TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    memory_count INTEGER NOT NULL DEFAULT 0,
                    new_memory_ids TEXT DEFAULT '[]',
                    superseded_skills TEXT DEFAULT '[]',
                    mutation_summary TEXT DEFAULT ''
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_evolution_skill ON evolution_records(skill_slug)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_evolution_cluster ON evolution_records(cluster_id)"
            )

    # ── Cluster CRUD ──

    def save_cluster(
        self,
        cluster_id: str,
        topic: str,
        centroid: Optional[List[float]] = None,
        skill_slug: Optional[str] = None,
        superseded_slugs: Optional[List[str]] = None,
    ) -> str:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            centroid_blob = pickle.dumps(centroid) if centroid else None
            superseded_json = json.dumps(superseded_slugs or [], ensure_ascii=False)
            cursor.execute("""
                INSERT OR REPLACE INTO knowledge_clusters
                    (cluster_id, topic, centroid, skill_slug, superseded_slugs,
                     created_at, last_updated_at)
                VALUES (?, ?, ?, ?, ?,
                    COALESCE((SELECT created_at FROM knowledge_clusters WHERE cluster_id = ?), CURRENT_TIMESTAMP),
                    CURRENT_TIMESTAMP)
            """, (cluster_id, topic, centroid_blob, skill_slug, superseded_json, cluster_id))
        return cluster_id

    def get_cluster(self, cluster_id: str) -> Optional[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM knowledge_clusters WHERE cluster_id = ?", (cluster_id,))
            row = cursor.fetchone()
            if not row:
                return None
            cursor.execute(
                "SELECT memory_id FROM cluster_members WHERE cluster_id = ? ORDER BY added_at",
                (cluster_id,),
            )
            memory_ids = [r["memory_id"] for r in cursor.fetchall()]
            return self._row_to_cluster_dict(row, memory_ids)

    def get_all_clusters(self) -> List[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM knowledge_clusters ORDER BY last_updated_at DESC")
            rows = cursor.fetchall()
            if not rows:
                return []
            by_cluster = self._members_by_cluster_id(conn)
            return [self._row_to_cluster_dict(row, by_cluster.get(row["cluster_id"], [])) for row in rows]

    def get_cluster_dicts_ready_for_crystallization(self, min_members: int) -> List[dict]:
        """Clusters with at least ``min_members`` and no skill yet (DB-side filter)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT k.*
                FROM knowledge_clusters k
                INNER JOIN (
                    SELECT cluster_id
                    FROM cluster_members
                    GROUP BY cluster_id
                    HAVING COUNT(*) >= ?
                ) m ON m.cluster_id = k.cluster_id
                WHERE (k.skill_slug IS NULL OR k.skill_slug = '')
                ORDER BY k.last_updated_at DESC
                """,
                (min_members,),
            )
            rows = cursor.fetchall()
            if not rows:
                return []
            by_cluster = self._members_by_cluster_id(conn)
            return [self._row_to_cluster_dict(row, by_cluster.get(row["cluster_id"], [])) for row in rows]

    def get_clusters_with_centroids(self) -> List[Tuple[dict, List[float]]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM knowledge_clusters WHERE centroid IS NOT NULL")
            rows = cursor.fetchall()
            if not rows:
                return []
            by_cluster = self._members_by_cluster_id(conn)
            results = []
            for row in rows:
                cluster_dict = self._row_to_cluster_dict(row, by_cluster.get(row["cluster_id"], []))
                centroid = pickle.loads(row["centroid"]) if row["centroid"] else []
                results.append((cluster_dict, centroid))
            return results

    def update_cluster_skill(self, cluster_id: str, skill_slug: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE knowledge_clusters SET skill_slug = ?, last_updated_at = CURRENT_TIMESTAMP WHERE cluster_id = ?",
                (skill_slug, cluster_id),
            )
            return cursor.rowcount > 0

    def update_cluster_centroid(self, cluster_id: str, centroid: List[float]) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE knowledge_clusters SET centroid = ?, last_updated_at = CURRENT_TIMESTAMP WHERE cluster_id = ?",
                (pickle.dumps(centroid), cluster_id),
            )
            return cursor.rowcount > 0

    def update_cluster_topic(self, cluster_id: str, topic: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE knowledge_clusters SET topic = ?, last_updated_at = CURRENT_TIMESTAMP WHERE cluster_id = ?",
                (topic, cluster_id),
            )
            return cursor.rowcount > 0

    # ── Cluster members ──

    def add_cluster_member(self, cluster_id: str, memory_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO cluster_members (cluster_id, memory_id) VALUES (?, ?)",
                    (cluster_id, memory_id),
                )
                if cursor.rowcount > 0:
                    cursor.execute(
                        "UPDATE knowledge_clusters SET last_updated_at = CURRENT_TIMESTAMP WHERE cluster_id = ?",
                        (cluster_id,),
                    )
                return cursor.rowcount > 0
            except sqlite3.IntegrityError:
                return False

    def get_cluster_member_ids(self, cluster_id: str) -> List[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT memory_id FROM cluster_members WHERE cluster_id = ? ORDER BY added_at",
                (cluster_id,),
            )
            return [row["memory_id"] for row in cursor.fetchall()]

    def get_cluster_for_memory(self, memory_id: str) -> Optional[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT cluster_id FROM cluster_members WHERE memory_id = ?",
                (memory_id,),
            )
            row = cursor.fetchone()
            return row["cluster_id"] if row else None

    def count_cluster_members_since(self, cluster_id: str, since_skill_slug: str) -> int:
        """Count members added after the last crystallization for this skill on this cluster."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if since_skill_slug:
                cursor.execute(
                    """SELECT MAX(timestamp) as last_evolve FROM evolution_records
                       WHERE cluster_id = ? AND skill_slug = ?
                         AND status IN ('crystallized', 'recrystallized')""",
                    (cluster_id, since_skill_slug),
                )
            else:
                cursor.execute(
                    """SELECT MAX(timestamp) as last_evolve FROM evolution_records
                       WHERE cluster_id = ? AND status IN ('crystallized', 'recrystallized')""",
                    (cluster_id,),
                )
            row = cursor.fetchone()
            last_evolve = row["last_evolve"] if row and row["last_evolve"] else None
            if last_evolve:
                cursor.execute(
                    "SELECT COUNT(*) FROM cluster_members WHERE cluster_id = ? AND added_at > ?",
                    (cluster_id, last_evolve),
                )
            else:
                cursor.execute(
                    "SELECT COUNT(*) FROM cluster_members WHERE cluster_id = ?",
                    (cluster_id,),
                )
            return cursor.fetchone()[0]

    # ── Evolution records ──

    def save_evolution_record(
        self,
        skill_slug: str,
        cluster_id: str,
        old_version: Optional[str],
        new_version: str,
        old_score: Optional[float],
        new_score: float,
        status: str,
        trigger: str,
        memory_count: int,
        new_memory_ids: Optional[List[str]] = None,
        superseded_skills: Optional[List[str]] = None,
        mutation_summary: str = "",
    ) -> str:
        record_id = str(uuid.uuid4())
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO evolution_records
                    (id, skill_slug, cluster_id, old_version, new_version,
                     old_score, new_score, status, trigger, memory_count,
                     new_memory_ids, superseded_skills, mutation_summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record_id, skill_slug, cluster_id, old_version, new_version,
                old_score, new_score, status, trigger, memory_count,
                json.dumps(new_memory_ids or [], ensure_ascii=False),
                json.dumps(superseded_skills or [], ensure_ascii=False),
                mutation_summary,
            ))
        return record_id

    def get_evolution_history(self, skill_slug: str, limit: int = 20) -> List[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM evolution_records WHERE skill_slug = ? ORDER BY timestamp DESC LIMIT ?",
                (skill_slug, limit),
            )
            return [self._row_to_evolution_dict(row) for row in cursor.fetchall()]

    # ── Row converters ──

    @staticmethod
    def _members_by_cluster_id(conn) -> dict:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT cluster_id, memory_id FROM cluster_members ORDER BY cluster_id, added_at",
        )
        by_cluster: dict = defaultdict(list)
        for r in cursor.fetchall():
            by_cluster[r["cluster_id"]].append(r["memory_id"])
        return dict(by_cluster)

    def _row_to_cluster_dict(self, row: sqlite3.Row, memory_ids: List[str]) -> dict:
        centroid = []
        if row["centroid"]:
            try:
                centroid = pickle.loads(row["centroid"])
            except Exception:
                centroid = []
        superseded = []
        if row["superseded_slugs"]:
            try:
                superseded = json.loads(row["superseded_slugs"])
            except (json.JSONDecodeError, TypeError):
                superseded = []
        return {
            "cluster_id": row["cluster_id"],
            "topic": row["topic"],
            "centroid": centroid,
            "memory_ids": memory_ids,
            "skill_slug": row["skill_slug"],
            "superseded_slugs": superseded,
            "created_at": row["created_at"],
            "last_updated_at": row["last_updated_at"],
        }

    def _row_to_evolution_dict(self, row: sqlite3.Row) -> dict:
        new_memory_ids = []
        if row["new_memory_ids"]:
            try:
                new_memory_ids = json.loads(row["new_memory_ids"])
            except (json.JSONDecodeError, TypeError):
                pass
        superseded = []
        if row["superseded_skills"]:
            try:
                superseded = json.loads(row["superseded_skills"])
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "id": row["id"],
            "skill_slug": row["skill_slug"],
            "cluster_id": row["cluster_id"],
            "timestamp": row["timestamp"],
            "old_version": row["old_version"],
            "new_version": row["new_version"],
            "old_score": row["old_score"],
            "new_score": row["new_score"],
            "status": row["status"],
            "trigger": row["trigger"],
            "memory_count": row["memory_count"],
            "new_memory_ids": new_memory_ids,
            "superseded_skills": superseded,
            "mutation_summary": row["mutation_summary"],
        }
