# Copyright (c) ModelScope Contributors. All rights reserved.
"""SQLite helpers for ingestion progress and raw-upload archive."""
import base64
import json
import uuid
from typing import List, Optional


class _IngestionMixin:
    """DB operations for ingestion cursors and raw user upload archive."""

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
