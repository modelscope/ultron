# Copyright (c) ModelScope Contributors. All rights reserved.
"""SQLite helpers for trajectory_records (metric labeling + memory extraction pipeline).

Only ``quality_metrics`` stores analysis JSON for task segments; row dicts include
derived ``quality_score`` and ``task_type`` from ``ultron.core.quality_json`` for callers.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional, Union

from .quality_json import (
    enrich_task_segment_row,
    enrich_trajectory_row,
    json_summary_overall_score_norm_sql,
)

_QS_NORM = json_summary_overall_score_norm_sql()


def _unit_interval(x: Union[float, int]) -> float:
    """Clamp a quality score or comparison threshold to [0, 1]."""
    return max(0.0, min(1.0, float(x)))


class _TrajectoryMixin:
    """DB operations for trajectory_records table."""

    def _ensure_trajectory_tables(self) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS trajectory_records (
                    id TEXT PRIMARY KEY,
                    task_text TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    model_used TEXT DEFAULT '',
                    success INTEGER DEFAULT 1,
                    latency_ms INTEGER,
                    quality_metrics TEXT DEFAULT '',
                    source_agent_id TEXT DEFAULT '',
                    tool_call_count INTEGER DEFAULT 0,
                    response_length INTEGER DEFAULT 0,
                    labeled INTEGER DEFAULT 0,
                    memory_extracted INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._migrate_trajectory_columns(conn)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_traj_labeled ON trajectory_records(labeled)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_traj_created ON trajectory_records(created_at)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_traj_session_pair ON trajectory_records(source_agent_id, session_file, pair_index)"
            )

    def _migrate_trajectory_columns(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(trajectory_records)")
        cols = {row[1] for row in cur.fetchall()}
        if "session_file" not in cols:
            cur.execute(
                "ALTER TABLE trajectory_records ADD COLUMN session_file TEXT DEFAULT ''"
            )
        if "pair_index" not in cols:
            cur.execute(
                "ALTER TABLE trajectory_records ADD COLUMN pair_index INTEGER DEFAULT -1"
            )
        if "segmented" not in cols:
            cur.execute(
                "ALTER TABLE trajectory_records ADD COLUMN segmented INTEGER DEFAULT 0"
            )
        if "quality_metrics" not in cols:
            cur.execute(
                "ALTER TABLE trajectory_records ADD COLUMN quality_metrics TEXT DEFAULT ''"
            )

    def save_session_trajectory(
        self,
        *,
        traj_id: str,
        session_file: str,
        source_agent_id: str = "",
    ) -> str:
        """Save one session-level row (pair_index=-1). Uses INSERT OR IGNORE for idempotency."""
        with self._get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO trajectory_records
                (id, task_text, response_text, model_used, success, latency_ms,
                 source_agent_id, tool_call_count, response_length, labeled, memory_extracted,
                 session_file, pair_index)
                VALUES (?, ?, '', '', 1, NULL, ?, 0, 0, 0, 0, ?, -1)""",
                (traj_id, session_file or "", source_agent_id or "", session_file or ""),
            )
        return traj_id

    def get_session_row(self, source_agent_id: str, session_file: str) -> Optional[dict]:
        """Return the session-level row (pair_index=-1) for this session, or None."""
        with self._get_connection() as conn:
            row = conn.execute(
                """SELECT * FROM trajectory_records
                WHERE source_agent_id=? AND session_file=? AND pair_index=-1
                ORDER BY created_at ASC LIMIT 1""",
                (source_agent_id or "", session_file or ""),
            ).fetchone()
        return self._row_to_traj_dict(row) if row else None

    def update_trajectory_metrics(self, traj_id: str, quality_metrics: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """UPDATE trajectory_records
                SET quality_metrics=?, labeled=1
                WHERE id=?""",
                (quality_metrics or "", traj_id),
            )

    def mark_memory_extracted(self, traj_id: str) -> None:
        """Mark a trajectory record as having its memory extracted (used by import scripts)."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE trajectory_records SET memory_extracted=1 WHERE id=?",
                (traj_id,),
            )

    def query_trajectories(
        self,
        task_type: Optional[str] = None,
        min_quality_score: Optional[float] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        where: List[str] = []
        params: List[Any] = []
        if min_quality_score is not None:
            m = _unit_interval(min_quality_score)
            where.append(f"({_QS_NORM}) IS NOT NULL AND ({_QS_NORM}) >= ?")
            params.append(m)
        if task_type:
            where.append(
                "json_extract(quality_metrics, '$.summary.task_type') = ?"
            )
            params.append(task_type)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        params.extend([max(1, int(limit)), max(0, int(offset))])
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""SELECT * FROM trajectory_records {clause}
                ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                params,
            )
            return [self._row_to_traj_dict(r) for r in cur.fetchall()]

    def get_trajectory_stats(self) -> dict:
        with self._get_connection() as conn:
            cur = conn.cursor()
            total = cur.execute("SELECT COUNT(*) FROM trajectory_records").fetchone()[0]
            labeled = cur.execute(
                "SELECT COUNT(*) FROM trajectory_records WHERE labeled=1"
            ).fetchone()[0]
            memory_eligible = cur.execute(
                f"""SELECT COUNT(*) FROM trajectory_records
                WHERE labeled=1
                  AND IFNULL(quality_metrics, '') != ''
                  AND json_extract(quality_metrics, '$.summary.overall_score') IS NOT NULL
                  AND ({_QS_NORM}) IS NOT NULL
                  AND ({_QS_NORM}) >= 0.7"""
            ).fetchone()[0]
            sft_eligible = cur.execute(
                f"""SELECT COUNT(*) FROM trajectory_records
                WHERE labeled=1
                  AND IFNULL(quality_metrics, '') != ''
                  AND json_extract(quality_metrics, '$.summary.overall_score') IS NOT NULL
                  AND ({_QS_NORM}) IS NOT NULL
                  AND ({_QS_NORM}) >= 0.8"""
            ).fetchone()[0]
            avg_score = cur.execute(
                f"""SELECT AVG({_QS_NORM}) FROM trajectory_records
                WHERE labeled=1
                  AND IFNULL(quality_metrics, '') != ''
                  AND ({_QS_NORM}) IS NOT NULL"""
            ).fetchone()[0]
            extracted = cur.execute(
                "SELECT COUNT(*) FROM trajectory_records WHERE memory_extracted=1"
            ).fetchone()[0]
        return {
            "total": int(total),
            "labeled": int(labeled),
            "memory_eligible": int(memory_eligible),
            "sft_eligible": int(sft_eligible),
            "avg_quality_score": float(avg_score or 0.0),
            "memory_extracted": int(extracted),
        }

    def get_unsegmented_sessions(self, limit: int) -> List[dict]:
        """Return session-level rows (pair_index=-1) that have not been segmented yet."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT * FROM trajectory_records
                WHERE pair_index=-1 AND IFNULL(session_file, '') != ''
                AND segmented=0
                ORDER BY created_at ASC LIMIT ?""",
                (max(1, int(limit)),),
            )
            return [self._row_to_traj_dict(r) for r in cur.fetchall()]

    def mark_session_segmented(self, source_agent_id: str, session_file: str) -> None:
        """Mark the session-level row as segmented."""
        with self._get_connection() as conn:
            conn.execute(
                """UPDATE trajectory_records SET segmented=1
                WHERE source_agent_id=? AND session_file=? AND pair_index=-1""",
                (source_agent_id or "", session_file or ""),
            )

    # ============ Task Segments ============

    def _ensure_task_segments_table(self) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS task_segments (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    session_file TEXT NOT NULL,
                    segment_index INTEGER NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    fingerprint TEXT NOT NULL,
                    topic TEXT DEFAULT '',
                    quality_metrics TEXT DEFAULT '',
                    labeled INTEGER DEFAULT 0,
                    memory_extracted INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(agent_id, session_file, fingerprint)
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_seg_session ON task_segments(agent_id, session_file)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_seg_labeled ON task_segments(labeled)"
            )
            cur.execute("PRAGMA table_info(task_segments)")
            cols = {row[1] for row in cur.fetchall()}
            if "quality_metrics" not in cols:
                cur.execute(
                    "ALTER TABLE task_segments ADD COLUMN quality_metrics TEXT DEFAULT ''"
                )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_seg_labeled_mem ON task_segments(labeled, memory_extracted)"
            )

    def save_task_segment(
        self,
        *,
        segment_id: str,
        agent_id: str,
        session_file: str,
        segment_index: int,
        start_line: int,
        end_line: int,
        fingerprint: str,
        topic: str = "",
    ) -> bool:
        """Save one task segment. Returns True if inserted, False if fingerprint already exists."""
        with self._get_connection() as conn:
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO task_segments
                    (id, agent_id, session_file, segment_index, start_line, end_line,
                     fingerprint, topic, labeled, memory_extracted)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0)""",
                    (segment_id, agent_id or "", session_file, segment_index,
                     start_line, end_line, fingerprint, topic or ""),
                )
                return conn.total_changes > 0
            except Exception:
                return False

    def get_segments_for_session(
        self, agent_id: str, session_file: str
    ) -> List[dict]:
        """Return all segments for a session, ordered by segment_index."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT * FROM task_segments
                WHERE agent_id=? AND session_file=?
                ORDER BY segment_index ASC""",
                (agent_id or "", session_file or ""),
            )
            return [self._row_to_seg_dict(r) for r in cur.fetchall()]

    def get_unlabeled_segments(self, limit: int) -> List[dict]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT * FROM task_segments WHERE labeled=0
                ORDER BY created_at ASC LIMIT ?""",
                (max(1, int(limit)),),
            )
            return [self._row_to_seg_dict(r) for r in cur.fetchall()]

    def update_segment_metrics(self, segment_id: str, quality_metrics: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """UPDATE task_segments
                SET quality_metrics=?, labeled=1,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?""",
                (quality_metrics or "", segment_id),
            )

    def get_memory_eligible_unextracted_segments(
        self,
        limit: int,
        min_quality_score: Union[float, int] = 0.7,
    ) -> List[dict]:
        min_score = _unit_interval(min_quality_score)
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""SELECT * FROM task_segments
                WHERE labeled=1 AND memory_extracted=0
                  AND quality_metrics != ''
                  AND json_extract(quality_metrics, '$.summary.overall_score') IS NOT NULL
                  AND ({_QS_NORM}) >= ?
                ORDER BY created_at ASC LIMIT ?""",
                (min_score, max(1, int(limit))),
            )
            return [self._row_to_seg_dict(r) for r in cur.fetchall()]

    def mark_segment_memory_extracted(self, segment_id: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """UPDATE task_segments SET memory_extracted=1,
                   updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (segment_id,),
            )

    def reset_task_segments_memory_extracted(
        self,
        *,
        session_file_contains: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> int:
        """Set ``memory_extracted=0`` for matching ``task_segments`` rows (re-run extraction later).

        At least one of ``session_file_contains`` or ``agent_id`` must be non-empty (safety).
        If both are set, rows must match both conditions.

        Returns:
            Number of rows updated.
        """
        sfc = (session_file_contains or "").strip()
        aid = (agent_id or "").strip()
        if not sfc and not aid:
            raise ValueError(
                "refusing unscoped reset: pass session_file_contains and/or agent_id"
            )
        where_clauses: List[str] = []
        params: List[Any] = []
        if sfc:
            where_clauses.append("session_file LIKE ?")
            params.append(f"%{sfc}%")
        if aid:
            where_clauses.append("agent_id = ?")
            params.append(aid)
        where_sql = " AND ".join(where_clauses)
        sql = f"""UPDATE task_segments SET memory_extracted=0,
                  updated_at=CURRENT_TIMESTAMP
                  WHERE {where_sql}"""
        with self._get_connection() as conn:
            cur = conn.execute(sql, params)
            return int(cur.rowcount or 0)

    def delete_segment(self, segment_id: str) -> None:
        """Delete a segment row (used when its fingerprint is superseded)."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM task_segments WHERE id=?", (segment_id,))

    def has_segments_for_session(self, agent_id: str, session_file: str) -> bool:
        """Return True if this session has any task_segments rows."""
        with self._get_connection() as conn:
            row = conn.execute(
                """SELECT COUNT(*) FROM task_segments
                WHERE agent_id=? AND session_file=?""",
                (agent_id or "", session_file or ""),
            ).fetchone()
        return bool(row and int(row[0]) > 0)

    def get_segment_stats(self) -> dict:
        with self._get_connection() as conn:
            cur = conn.cursor()
            total = cur.execute("SELECT COUNT(*) FROM task_segments").fetchone()[0]
            labeled = cur.execute(
                "SELECT COUNT(*) FROM task_segments WHERE labeled=1"
            ).fetchone()[0]
            memory_eligible = cur.execute(
                f"""SELECT COUNT(*) FROM task_segments
                WHERE labeled=1
                  AND quality_metrics != ''
                  AND json_extract(quality_metrics, '$.summary.overall_score') IS NOT NULL
                  AND ({_QS_NORM}) >= 0.7"""
            ).fetchone()[0]
            sft_eligible = cur.execute(
                f"""SELECT COUNT(*) FROM task_segments
                WHERE labeled=1
                  AND quality_metrics != ''
                  AND json_extract(quality_metrics, '$.summary.overall_score') IS NOT NULL
                  AND ({_QS_NORM}) >= 0.8"""
            ).fetchone()[0]
            avg_score = cur.execute(
                f"""SELECT AVG({_QS_NORM}) FROM task_segments
                WHERE labeled=1
                  AND quality_metrics != ''
                  AND ({_QS_NORM}) IS NOT NULL"""
            ).fetchone()[0]
            excellent = cur.execute(
                f"""SELECT COUNT(*) FROM task_segments
                WHERE labeled=1
                  AND quality_metrics != ''
                  AND ({_QS_NORM}) IS NOT NULL
                  AND ({_QS_NORM}) >= 0.85"""
            ).fetchone()[0]
            usable = cur.execute(
                f"""SELECT COUNT(*) FROM task_segments
                WHERE labeled=1
                  AND quality_metrics != ''
                  AND ({_QS_NORM}) IS NOT NULL
                  AND ({_QS_NORM}) >= 0.7 AND ({_QS_NORM}) < 0.85"""
            ).fetchone()[0]
            weak = cur.execute(
                f"""SELECT COUNT(*) FROM task_segments
                WHERE labeled=1
                  AND (quality_metrics = '' OR quality_metrics IS NULL
                       OR json_extract(quality_metrics, '$.summary.overall_score') IS NULL
                       OR ({_QS_NORM}) < 0.7)"""
            ).fetchone()[0]
            extracted = cur.execute(
                "SELECT COUNT(*) FROM task_segments WHERE memory_extracted=1"
            ).fetchone()[0]
        return {
            "total": int(total),
            "labeled": int(labeled),
            "memory_eligible": int(memory_eligible),
            "sft_eligible": int(sft_eligible),
            "avg_quality_score": float(avg_score or 0.0),
            "score_buckets": {
                "excellent": int(excellent),
                "usable": int(usable),
                "weak": int(weak),
            },
            "memory_extracted": int(extracted),
        }

    def get_segments_for_sft(
        self,
        task_type: Optional[str] = None,
        limit: int = 5000,
        min_quality_score: Union[float, int] = 0.8,
    ) -> List[dict]:
        """Return metric-qualified segments for SFT export."""
        min_s = _unit_interval(min_quality_score)
        where = (
            "labeled=1 AND quality_metrics != '' "
            "AND json_extract(quality_metrics, '$.summary.overall_score') IS NOT NULL "
            f"AND ({_QS_NORM}) IS NOT NULL AND ({_QS_NORM}) >= ?"
        )
        params: List[Any] = [min_s]
        if task_type:
            where += " AND json_extract(quality_metrics, '$.summary.task_type') = ?"
            params.append(task_type)
        params.append(max(1, int(limit)))
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""SELECT * FROM task_segments WHERE {where}
                ORDER BY created_at ASC LIMIT ?""",
                params,
            )
            return [self._row_to_seg_dict(r) for r in cur.fetchall()]

    @staticmethod
    def _row_to_seg_dict(row: sqlite3.Row) -> dict:
        d = {k: row[k] for k in row.keys()}
        return enrich_task_segment_row(d)

    @staticmethod
    def _row_to_traj_dict(row: sqlite3.Row) -> dict:
        d = {k: row[k] for k in row.keys()}
        return enrich_trajectory_row(d)
