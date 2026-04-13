# Copyright (c) ModelScope Contributors. All rights reserved.
"""Database mixin for user account CRUD (authentication support)."""

import sqlite3


class _UserMixin:
    """User table operations — mixed into Database."""

    def create_user(self, username: str, password_hash: str) -> dict:
        """Insert a new user. Raises ValueError if username already taken."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, password_hash),
                )
            except sqlite3.IntegrityError:
                raise ValueError(f"Username '{username}' is already taken")
            cursor.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,))
            return self._row_to_user_dict(cursor.fetchone())

    def get_user_by_username(self, username: str):
        """Return user dict or None."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            return self._row_to_user_dict(row) if row else None

    def _row_to_user_dict(self, row) -> dict:
        return {
            "id": row["id"],
            "username": row["username"],
            "password_hash": row["password_hash"],
            "created_at": row["created_at"],
        }
