# Copyright (c) ModelScope Contributors. All rights reserved.
import json
import pickle
import sqlite3
import uuid
import base64
from typing import List, Optional, Tuple

from .models import MemoryRecord


class _MemoryMixin:
    """Memory records, session-extract progress, and raw-upload archive operations."""

    def save_memory_record(self, record: MemoryRecord) -> str:
        with self._get_connection() as conn:
            cursor = conn.cursor()

            embedding_blob = None
            if record.embedding:
                embedding_blob = pickle.dumps(record.embedding)

            tags_json = json.dumps(record.tags, ensure_ascii=False) if record.tags else "[]"

            cursor.execute("""
                INSERT OR REPLACE INTO memory_records (
                    id, memory_type, content, context, resolution,
                    tier, hit_count, status,
                    generated_skill_slug, tags,
                    embedding, created_at, last_hit_at, updated_at,
                    summary_l0, overview_l1
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
            """, (
                record.id,
                record.memory_type,
                record.content,
                record.context,
                record.resolution,
                record.tier,
                record.hit_count,
                record.status,
                record.generated_skill_slug,
                tags_json,
                embedding_blob,
                record.created_at.isoformat(),
                record.last_hit_at.isoformat(),
                getattr(record, 'summary_l0', ''),
                getattr(record, 'overview_l1', ''),
            ))

            return record.id

    def get_memory_record(self, memory_id: str) -> Optional[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM memory_records WHERE id = ?", (memory_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_memory_dict(row)
            return None

    def get_memory_records_by_tier(
        self,
        tier: str,
        limit: int = 100,
    ) -> List[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM memory_records WHERE tier = ?"
            params: list = [tier]

            query += " ORDER BY hit_count DESC, last_hit_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            return [self._row_to_memory_dict(row) for row in cursor.fetchall()]

    def get_memory_records_with_embeddings(
        self,
        memory_type: Optional[str] = None,
        tier: Optional[str] = None,
    ) -> List[Tuple[dict, List[float]]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM memory_records WHERE embedding IS NOT NULL AND status != 'archived'"
            params: list = []

            if memory_type:
                query += " AND memory_type = ?"
                params.append(memory_type)
            if tier:
                query += " AND tier = ?"
                params.append(tier)

            cursor.execute(query, params)
            results = []
            for row in cursor.fetchall():
                memory_dict = self._row_to_memory_dict(row)
                embedding = pickle.loads(row["embedding"]) if row["embedding"] else []
                results.append((memory_dict, embedding))
            return results

    def increment_memory_hit(
        self,
        memory_id: str,
        content: str = "",
        context: str = "",
        resolution: str = "",
    ) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if content or resolution:
                cursor.execute("""
                    INSERT INTO memory_contributions
                        (memory_id, content, context, resolution, contributed_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (memory_id, content, context, resolution))

            cursor.execute("""
                UPDATE memory_records
                SET hit_count = hit_count + 1,
                    last_hit_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (memory_id,))

            cursor.execute("SELECT * FROM memory_records WHERE id = ?", (memory_id,))
            row = cursor.fetchone()
            return self._row_to_memory_dict(row) if row else {}

    def increment_memory_hit_light(
        self,
        memory_id: str,
        weight: int = 1,
    ) -> dict:
        """Lightweight hit increment for search/details adoption tracking."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE memory_records
                SET hit_count = hit_count + ?,
                    last_hit_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (weight, memory_id))
            cursor.execute("SELECT * FROM memory_records WHERE id = ?", (memory_id,))
            row = cursor.fetchone()
            return self._row_to_memory_dict(row) if row else {}

    def update_memory_merged_body(
        self,
        memory_id: str,
        content: str,
        context: str,
        resolution: str,
        embedding: List[float],
        summary_l0: str,
        overview_l1: str,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """Persist merged body text, embedding, and L0/L1 summaries after near-duplicate merge."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            embedding_blob = pickle.dumps(embedding) if embedding else None
            core = (
                content,
                context,
                resolution,
                embedding_blob,
                summary_l0,
                overview_l1,
            )
            if tags is not None:
                tags_json = json.dumps(tags, ensure_ascii=False) if tags else "[]"
                cursor.execute("""
                    UPDATE memory_records SET
                        content = ?, context = ?, resolution = ?,
                        embedding = ?, summary_l0 = ?, overview_l1 = ?,
                        tags = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (*core, tags_json, memory_id))
            else:
                cursor.execute("""
                    UPDATE memory_records SET
                        content = ?, context = ?, resolution = ?,
                        embedding = ?, summary_l0 = ?, overview_l1 = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (*core, memory_id))
            return cursor.rowcount > 0

    def get_memory_contributions(self, memory_id: str) -> List[dict]:
        """Return contribution rows for a memory, oldest first."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM memory_contributions
                WHERE memory_id = ?
                ORDER BY contributed_at ASC
            """, (memory_id,))
            return [
                {
                    "content": row["content"],
                    "context": row["context"],
                    "resolution": row["resolution"],
                    "contributed_at": row["contributed_at"],
                }
                for row in cursor.fetchall()
            ]

    def update_memory_tier(self, memory_id: str, new_tier: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE memory_records SET tier = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_tier, memory_id)
            )
            return cursor.rowcount > 0

    def update_memory_status(self, memory_id: str, new_status: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE memory_records SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_status, memory_id)
            )
            return cursor.rowcount > 0

    def update_memory_generated_skill(self, memory_id: str, skill_slug: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE memory_records SET generated_skill_slug = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (skill_slug, memory_id)
            )
            return cursor.rowcount > 0

    def get_warm_overflow_candidates(self, max_warm: int) -> List[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM memory_records WHERE tier = 'warm'")
            warm_count = cursor.fetchone()[0]
            if warm_count <= max_warm:
                return []
            overflow = warm_count - max_warm
            cursor.execute("""
                SELECT * FROM memory_records
                WHERE tier = 'warm'
                ORDER BY hit_count ASC, last_hit_at ASC
                LIMIT ?
            """, (overflow,))
            return [self._row_to_memory_dict(row) for row in cursor.fetchall()]

    def get_all_memory_ids_ranked(self) -> List[Tuple[str, str]]:
        """Return (id, current_tier) for all non-archived memories, ranked by hit_count DESC, last_hit_at DESC."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, tier FROM memory_records
                WHERE status != 'archived'
                ORDER BY hit_count DESC, last_hit_at DESC
            """)
            return [(row["id"], row["tier"]) for row in cursor.fetchall()]

    def batch_update_tiers(self, updates: List[Tuple[str, str]]) -> int:
        """Batch update tier for a list of (memory_id, new_tier) pairs. Returns count of rows changed."""
        if not updates:
            return 0
        changed = 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for memory_id, new_tier in updates:
                cursor.execute(
                    "UPDATE memory_records SET tier = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (new_tier, memory_id),
                )
                changed += cursor.rowcount
        return changed

    def migrate_legacy_statuses(self) -> int:
        """Migrate old status values (tentative/emerging/pending/confirmed) to 'active'."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE memory_records
                SET status = 'active', updated_at = CURRENT_TIMESTAMP
                WHERE status IN ('tentative', 'emerging', 'pending', 'confirmed')
            """)
            return cursor.rowcount

    def archive_stale_cold_memories(self, ttl_days: int) -> int:
        """Set status to 'archived' for COLD memories older than TTL days. Archived records are excluded from search and rebalance."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE memory_records
                SET status = 'archived', updated_at = CURRENT_TIMESTAMP
                WHERE tier = 'cold'
                  AND status != 'archived'
                  AND julianday('now') - julianday(last_hit_at) > ?
            """, (ttl_days,))
            return cursor.rowcount

    def count_memory_records(
        self,
        memory_type: Optional[str] = None,
        tier: Optional[str] = None,
    ) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT COUNT(*) FROM memory_records WHERE 1=1"
            params: list = []
            if memory_type:
                query += " AND memory_type = ?"
                params.append(memory_type)
            if tier:
                query += " AND tier = ?"
                params.append(tier)
            cursor.execute(query, params)
            return int(cursor.fetchone()[0])

    def get_memory_stats(self) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT tier, COUNT(*) as cnt FROM memory_records GROUP BY tier
            """)
            tier_counts = {row["tier"]: row["cnt"] for row in cursor.fetchall()}

            cursor.execute("""
                SELECT memory_type, COUNT(*) as cnt FROM memory_records GROUP BY memory_type
            """)
            type_counts = {row["memory_type"]: row["cnt"] for row in cursor.fetchall()}

            cursor.execute("""
                SELECT status, COUNT(*) as cnt FROM memory_records GROUP BY status
            """)
            status_counts = {row["status"]: row["cnt"] for row in cursor.fetchall()}

            cursor.execute("SELECT COUNT(*) FROM memory_records")
            total = int(cursor.fetchone()[0])

            return {
                "total": total,
                "by_tier": tier_counts,
                "by_type": type_counts,
                "by_status": status_counts,
            }

    def get_promotion_candidates(self) -> List[dict]:
        """HOT memories without an existing skill, for skill generation."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM memory_records
                WHERE tier = 'hot'
                  AND generated_skill_slug IS NULL
                ORDER BY hit_count DESC
            """)
            return [self._row_to_memory_dict(row) for row in cursor.fetchall()]

    def _row_to_memory_dict(self, row: sqlite3.Row) -> dict:
        tags = []
        if row["tags"]:
            try:
                tags = json.loads(row["tags"])
            except (json.JSONDecodeError, TypeError):
                tags = []

        embedding = None
        if row["embedding"]:
            try:
                embedding = pickle.loads(row["embedding"])
            except Exception:
                embedding = None

        return {
            "id": row["id"],
            "memory_type": row["memory_type"],
            "content": row["content"],
            "context": row["context"],
            "resolution": row["resolution"],
            "tier": row["tier"],
            "hit_count": row["hit_count"],
            "status": row["status"],
            "generated_skill_slug": row["generated_skill_slug"],
            "tags": tags,
            "embedding": embedding,
            "created_at": row["created_at"],
            "last_hit_at": row["last_hit_at"],
            "summary_l0": row["summary_l0"] if "summary_l0" in row.keys() else "",
            "overview_l1": row["overview_l1"] if "overview_l1" in row.keys() else "",
        }

    # ============ Session extract progress ============

    def get_session_extract_progress(self, agent_id: str, session_file: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT last_processed_lines FROM session_extract_progress WHERE agent_id = ? AND session_file = ?",
                (agent_id, session_file),
            )
            row = cursor.fetchone()
            return row["last_processed_lines"] if row else 0

    def update_session_extract_progress(self, agent_id: str, session_file: str, lines: int) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO session_extract_progress
                    (agent_id, session_file, last_processed_lines, last_extract_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (agent_id, session_file, lines))

    # ============ Raw user uploads ============

    # ============ Dashboard queries ============

    def search_memories_by_text(
        self,
        q: str = "",
        memory_type: str = "",
        tier: str = "",
        sort: str = "hit_count",
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[dict], int]:
        """Text search on memories with filters. Returns (rows, total_count)."""
        conditions = ["status = 'active'"]
        params: list = []

        if q:
            conditions.append("(content LIKE ? OR context LIKE ? OR resolution LIKE ? OR summary_l0 LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like, like])
        if memory_type:
            conditions.append("memory_type = ?")
            params.append(memory_type)
        if tier:
            conditions.append("tier = ?")
            params.append(tier)

        where = " AND ".join(conditions)
        order = "hit_count DESC" if sort == "hit_count" else "created_at DESC"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM memory_records WHERE {where}", params)
            total = cursor.fetchone()[0]

            cursor.execute(
                f"""SELECT id, memory_type, content, context, resolution, tier,
                           hit_count, status, tags, created_at, last_hit_at,
                           summary_l0, overview_l1
                    FROM memory_records WHERE {where}
                    ORDER BY {order} LIMIT ? OFFSET ?""",
                params + [limit, offset],
            )
            rows = []
            for r in cursor.fetchall():
                rows.append({
                    "id": r["id"],
                    "memory_type": r["memory_type"],
                    "content": r["content"],
                    "context": r["context"],
                    "resolution": r["resolution"],
                    "tier": r["tier"],
                    "hit_count": r["hit_count"],
                    "tags": json.loads(r["tags"]) if r["tags"] else [],
                    "created_at": r["created_at"],
                    "last_hit_at": r["last_hit_at"],
                    "summary_l0": r["summary_l0"] or "",
                    "overview_l1": r["overview_l1"] or "",
                })
            return rows, total

    def get_memory_leaderboard(self, limit: int = 50) -> dict:
        """Top memories per tier, ranked by hit_count."""
        result = {"hot": [], "warm": [], "cold": []}
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for t in ("hot", "warm", "cold"):
                cursor.execute(
                    """SELECT id, memory_type, summary_l0, tier, hit_count, created_at
                       FROM memory_records
                       WHERE tier = ? AND status = 'active'
                       ORDER BY hit_count DESC LIMIT ?""",
                    (t, limit),
                )
                for r in cursor.fetchall():
                    result[t].append({
                        "id": r["id"],
                        "memory_type": r["memory_type"],
                        "summary_l0": r["summary_l0"] or "",
                        "tier": r["tier"],
                        "hit_count": r["hit_count"],
                        "created_at": r["created_at"],
                    })
        return result

    def save_raw_user_upload(
        self,
        source: str,
        payload_blob: bytes,
        meta: Optional[dict] = None,
        http_method: str = "",
        http_path: str = "",
        upload_id: Optional[str] = None,
    ) -> str:
        rid = upload_id or str(uuid.uuid4())
        meta_json = json.dumps(meta or {}, ensure_ascii=False)
        sz = len(payload_blob) if payload_blob else 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO raw_user_uploads (
                    id, source, http_method, http_path, payload_blob, meta_json, payload_size
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (rid, source, http_method or "", http_path or "", payload_blob, meta_json, sz),
            )
        return rid

    def get_raw_user_upload(self, upload_id: str) -> Optional[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM raw_user_uploads WHERE id = ?", (upload_id,))
            row = cursor.fetchone()
            if not row:
                return None
            blob = row["payload_blob"]
            text_try = None
            if blob:
                try:
                    text_try = blob.decode("utf-8")
                except UnicodeDecodeError:
                    text_try = None
            return {
                "id": row["id"],
                "source": row["source"],
                "http_method": row["http_method"] or "",
                "http_path": row["http_path"] or "",
                "meta": json.loads(row["meta_json"] or "{}"),
                "payload_size": row["payload_size"],
                "created_at": row["created_at"],
                "payload_text": text_try,
                "payload_base64": base64.b64encode(blob).decode("ascii") if blob else "",
            }

    def list_raw_user_uploads(
        self,
        limit: int = 100,
        offset: int = 0,
        source_prefix: Optional[str] = None,
    ) -> List[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if source_prefix:
                cursor.execute(
                    """
                    SELECT id, source, http_method, http_path, payload_size, meta_json, created_at
                    FROM raw_user_uploads
                    WHERE source LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (f"{source_prefix}%", limit, offset),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, source, http_method, http_path, payload_size, meta_json, created_at
                    FROM raw_user_uploads
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )
            rows = cursor.fetchall()
        out = []
        for row in rows:
            out.append({
                "id": row["id"],
                "source": row["source"],
                "http_method": row["http_method"] or "",
                "http_path": row["http_path"] or "",
                "payload_size": row["payload_size"],
                "meta": json.loads(row["meta_json"] or "{}"),
                "created_at": row["created_at"],
            })
        return out
