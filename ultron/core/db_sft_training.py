# Copyright (c) ModelScope Contributors. All rights reserved.
"""SQLite helpers for SFT training run records."""
from __future__ import annotations

from typing import Any, List, Optional, Union

from .db_trajectory import _QS_NORM, _unit_interval


class _SFTTrainingMixin:
    """DB operations for SFT/self-training bookkeeping."""

    def _ensure_sft_training_table(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sft_training_records (
                    id TEXT PRIMARY KEY,
                    eligible_count_at_trigger INTEGER NOT NULL,
                    samples_exported INTEGER NOT NULL DEFAULT 0,
                    base_model TEXT NOT NULL DEFAULT '',
                    checkpoint_path TEXT DEFAULT '',
                    parent_checkpoint TEXT DEFAULT '',
                    epochs INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'pending',
                    error_message TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    finished_at TIMESTAMP
                )
                """
            )

    def save_sft_training_record(
        self,
        *,
        record_id: str,
        eligible_count: int,
        samples_exported: int,
        base_model: str,
        parent_checkpoint: str = "",
        epochs: int = 1,
        status: str = "pending",
    ) -> str:
        with self._get_connection() as conn:
            conn.execute(
                """INSERT INTO sft_training_records
                (id, eligible_count_at_trigger, samples_exported, base_model,
                 parent_checkpoint, epochs, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (record_id, eligible_count, samples_exported, base_model,
                 parent_checkpoint, epochs, status),
            )
        return record_id

    def update_sft_training_status(
        self,
        record_id: str,
        status: str,
        checkpoint_path: str = "",
        error_message: str = "",
    ) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """UPDATE sft_training_records
                SET status=?, checkpoint_path=?, error_message=?,
                    finished_at=CURRENT_TIMESTAMP
                WHERE id=?""",
                (status, checkpoint_path, error_message, record_id),
            )

    def get_latest_sft_checkpoint(self) -> Optional[str]:
        with self._get_connection() as conn:
            row = conn.execute(
                """SELECT checkpoint_path FROM sft_training_records
                WHERE status='completed' AND checkpoint_path != ''
                ORDER BY finished_at DESC LIMIT 1"""
            ).fetchone()
        return row[0] if row else None

    def get_last_sft_finished_at(self) -> Optional[str]:
        with self._get_connection() as conn:
            row = conn.execute(
                """SELECT finished_at FROM sft_training_records
                WHERE status='completed'
                ORDER BY finished_at DESC LIMIT 1"""
            ).fetchone()
        return row[0] if row and row[0] else None

    def get_sft_eligible_segment_count_since_last_sft(
        self, min_quality_score: Union[float, int] = 0.8,
    ) -> int:
        since = self.get_last_sft_finished_at()
        return self._count_sft_eligible_segments_since(since, min_quality_score)

    def _count_sft_eligible_segments_since(
        self, since: Optional[str], min_quality_score: Union[float, int] = 0.8,
    ) -> int:
        min_s = _unit_interval(min_quality_score)
        base = (
            "SELECT COUNT(*) FROM task_segments WHERE labeled=1 "
            "AND quality_metrics != '' "
            "AND json_extract(quality_metrics, '$.summary.overall_score') IS NOT NULL "
            f"AND ({_QS_NORM}) IS NOT NULL AND ({_QS_NORM}) >= ?"
        )
        with self._get_connection() as conn:
            if since:
                count = conn.execute(
                    f"{base} AND created_at > ?",
                    (min_s, since),
                ).fetchone()[0]
            else:
                count = conn.execute(
                    base,
                    (min_s,),
                ).fetchone()[0]
        return int(count)

    def get_segments_for_sft_since(
        self,
        since: Optional[str] = None,
        limit: int = 5000,
        min_quality_score: Union[float, int] = 0.8,
    ) -> List[dict]:
        min_s = _unit_interval(min_quality_score)
        where = (
            "labeled=1 AND quality_metrics != '' "
            "AND json_extract(quality_metrics, '$.summary.overall_score') IS NOT NULL "
            f"AND ({_QS_NORM}) IS NOT NULL AND ({_QS_NORM}) >= ?"
        )
        params: List[Any] = [min_s]
        if since:
            where += " AND created_at > ?"
            params.append(since)
        params.append(max(1, int(limit)))
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""SELECT * FROM task_segments WHERE {where}
                ORDER BY created_at ASC LIMIT ?""",
                params,
            )
            return [self._row_to_seg_dict(r) for r in cur.fetchall()]
