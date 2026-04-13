# Copyright (c) ModelScope Contributors. All rights reserved.
import json
from typing import List, Optional


class _HarnessMixin:
    """Device registry, profile storage, and share-token operations for HarnessHub."""

    # ============ Device operations ============

    def register_agent(
        self, user_id: str, agent_id: str, display_name: str = ""
    ) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO harness_agents
                    (user_id, agent_id, display_name, created_at, last_sync_at)
                VALUES (
                    ?, ?, ?,
                    COALESCE(
                        (SELECT created_at FROM harness_agents WHERE user_id = ? AND agent_id = ?),
                        CURRENT_TIMESTAMP
                    ),
                    (SELECT last_sync_at FROM harness_agents WHERE user_id = ? AND agent_id = ?)
                )
            """,
                (user_id, agent_id, display_name, user_id, agent_id, user_id, agent_id),
            )
            cursor.execute(
                "SELECT * FROM harness_agents WHERE user_id = ? AND agent_id = ?",
                (user_id, agent_id),
            )
            return self._row_to_agent_dict(cursor.fetchone())

    def list_agents(self, user_id: str) -> List[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM harness_agents WHERE user_id = ? ORDER BY created_at",
                (user_id,),
            )
            return [self._row_to_agent_dict(r) for r in cursor.fetchall()]

    def update_agent_sync(self, user_id: str, agent_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE harness_agents SET last_sync_at = CURRENT_TIMESTAMP WHERE user_id = ? AND agent_id = ?",
                (user_id, agent_id),
            )
            return cursor.rowcount > 0

    def delete_agent(self, user_id: str, agent_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM harness_shares WHERE source_user_id = ? AND source_agent_id = ?",
                (user_id, agent_id),
            )
            cursor.execute(
                "DELETE FROM harness_profiles WHERE user_id = ? AND agent_id = ?",
                (user_id, agent_id),
            )
            cursor.execute(
                "DELETE FROM harness_agents WHERE user_id = ? AND agent_id = ?",
                (user_id, agent_id),
            )
            return cursor.rowcount > 0

    # ============ Profile operations ============

    def upsert_profile(
        self,
        user_id: str,
        agent_id: str,
        resources_json: str,
        product: str = "nanobot",
    ) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT revision FROM harness_profiles WHERE user_id = ? AND agent_id = ?",
                (user_id, agent_id),
            )
            row = cursor.fetchone()
            new_rev = (row["revision"] + 1) if row else 1
            cursor.execute(
                """
                INSERT OR REPLACE INTO harness_profiles
                    (user_id, agent_id, revision, resources_json, product, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (user_id, agent_id, new_rev, resources_json, product),
            )
            # Auto-register agent if not exists, then update sync timestamp
            cursor.execute(
                """
                INSERT OR IGNORE INTO harness_agents
                    (user_id, agent_id, display_name, created_at, last_sync_at)
                VALUES (?, ?, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
                (user_id, agent_id),
            )
            cursor.execute(
                "UPDATE harness_agents SET last_sync_at = CURRENT_TIMESTAMP WHERE user_id = ? AND agent_id = ?",
                (user_id, agent_id),
            )
            cursor.execute(
                "SELECT * FROM harness_profiles WHERE user_id = ? AND agent_id = ?",
                (user_id, agent_id),
            )
            return self._row_to_profile_dict(cursor.fetchone())

    def get_profile(self, user_id: str, agent_id: str) -> Optional[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM harness_profiles WHERE user_id = ? AND agent_id = ?",
                (user_id, agent_id),
            )
            row = cursor.fetchone()
            return self._row_to_profile_dict(row) if row else None

    def get_profiles_by_user(self, user_id: str) -> List[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT agent_id, product, revision, updated_at FROM harness_profiles WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            )
            return [
                {
                    "agent_id": r["agent_id"],
                    "product": r["product"],
                    "revision": r["revision"],
                    "updated_at": r["updated_at"],
                }
                for r in cursor.fetchall()
            ]

    # ============ Share operations ============

    def create_share(
        self,
        token: str,
        source_user_id: str,
        source_agent_id: str,
        visibility: str,
        snapshot_json: str,
        short_code: str = "",
    ) -> dict:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO harness_shares
                    (token, short_code, source_user_id, source_agent_id, visibility, snapshot_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (token, short_code, source_user_id, source_agent_id, visibility, snapshot_json),
            )
            cursor.execute("SELECT * FROM harness_shares WHERE token = ?", (token,))
            return self._row_to_share_dict(cursor.fetchone())

    def get_share(self, token: str) -> Optional[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM harness_shares WHERE token = ?", (token,))
            row = cursor.fetchone()
            return self._row_to_share_dict(row) if row else None

    def get_share_by_agent(
        self, user_id: str, agent_id: str
    ) -> Optional[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM harness_shares "
                "WHERE source_user_id = ? AND source_agent_id = ? "
                "LIMIT 1",
                (user_id, agent_id),
            )
            row = cursor.fetchone()
            return self._row_to_share_dict(row) if row else None

    def update_share_snapshot(
        self, token: str, snapshot_json: str
    ) -> Optional[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE harness_shares SET snapshot_json = ? WHERE token = ?",
                (snapshot_json, token),
            )
            cursor.execute(
                "SELECT * FROM harness_shares WHERE token = ?", (token,)
            )
            row = cursor.fetchone()
            return self._row_to_share_dict(row) if row else None

    def get_share_by_code(self, short_code: str) -> Optional[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM harness_shares WHERE short_code = ?",
                (short_code,),
            )
            row = cursor.fetchone()
            return self._row_to_share_dict(row) if row else None

    def list_shares_by_user(self, user_id: str) -> List[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM harness_shares WHERE source_user_id = ? ORDER BY created_at DESC",
                (user_id,),
            )
            return [self._row_to_share_dict(r) for r in cursor.fetchall()]

    def delete_share(self, token: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM harness_shares WHERE token = ?", (token,))
            return cursor.rowcount > 0

    # ============ Row helpers ============

    def _row_to_agent_dict(self, row) -> dict:
        return {
            "user_id": row["user_id"],
            "agent_id": row["agent_id"],
            "display_name": row["display_name"] or "",
            "created_at": row["created_at"],
            "last_sync_at": row["last_sync_at"],
        }

    def _row_to_profile_dict(self, row) -> dict:
        resources = row["resources_json"] or "{}"
        try:
            resources = json.loads(resources)
        except (json.JSONDecodeError, TypeError):
            resources = {}
        return {
            "user_id": row["user_id"],
            "agent_id": row["agent_id"],
            "revision": row["revision"],
            "resources": resources,
            "product": row["product"],
            "updated_at": row["updated_at"],
        }

    def _row_to_share_dict(self, row) -> dict:
        snapshot = row["snapshot_json"] or "{}"
        try:
            snapshot = json.loads(snapshot)
        except (json.JSONDecodeError, TypeError):
            snapshot = {}
        return {
            "token": row["token"],
            "short_code": row["short_code"] if "short_code" in row.keys() else "",
            "source_user_id": row["source_user_id"],
            "source_agent_id": row["source_agent_id"],
            "visibility": row["visibility"],
            "snapshot": snapshot,
            "created_at": row["created_at"],
        }
