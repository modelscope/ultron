# Copyright (c) ModelScope Contributors. All rights reserved.
import json
import pickle
import sqlite3
from datetime import datetime
from typing import List, Optional, Tuple

from .models import (
    SkillMeta,
    SkillFrontmatter,
    SkillStatus,
)


class _SkillMixin:
    """Skill and category CRUD operations."""

    def save_skill(
        self,
        meta: SkillMeta,
        frontmatter: SkillFrontmatter,
        local_path: Optional[str] = None,
    ) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()

            embedding_blob = None
            if meta.embedding:
                embedding_blob = pickle.dumps(meta.embedding)

            cursor.execute("""
                INSERT OR REPLACE INTO skills (
                    slug, version, owner_id, published_at, parent_version, status,
                    name, description, categories, complexity, source_type,
                    embedding, local_path, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                meta.slug,
                meta.version,
                meta.owner_id,
                meta.published_at,
                meta.parent_version,
                meta.status.value if isinstance(meta.status, SkillStatus) else meta.status,
                frontmatter.name,
                frontmatter.description,
                json.dumps(frontmatter.categories, ensure_ascii=False),
                frontmatter.complexity,
                frontmatter.source_type,
                embedding_blob,
                local_path,
            ))

            return cursor.lastrowid

    def get_skill(self, slug: str, version: Optional[str] = None) -> Optional[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if version:
                cursor.execute(
                    "SELECT * FROM skills WHERE slug = ? AND version = ?",
                    (slug, version)
                )
            else:
                cursor.execute(
                    "SELECT * FROM skills WHERE slug = ? ORDER BY published_at DESC LIMIT 1",
                    (slug,)
                )

            row = cursor.fetchone()
            if row:
                return self._row_to_skill_dict(row)
            return None

    def get_all_skills(
        self,
        status: Optional[str] = None,
        categories: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM skills WHERE 1=1"
            params = []

            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY published_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            results = [self._row_to_skill_dict(row) for row in rows]

            if categories:
                results = [
                    r for r in results
                    if any(cat in r.get("categories", []) for cat in categories)
                ]

            return results

    def get_skills_with_embeddings(self) -> List[Tuple[dict, List[float]]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM skills WHERE embedding IS NOT NULL AND status = 'active'")
            rows = cursor.fetchall()

            results = []
            for row in rows:
                skill_dict = self._row_to_skill_dict(row)
                embedding = pickle.loads(row["embedding"]) if row["embedding"] else []
                results.append((skill_dict, embedding))

            return results

    def update_skill_status(self, slug: str, version: str, status: SkillStatus) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE skills SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE slug = ? AND version = ?",
                (status.value, slug, version)
            )
            return cursor.rowcount > 0

    def _row_to_skill_dict(self, row: sqlite3.Row) -> dict:
        categories = []
        if row["categories"]:
            try:
                categories = json.loads(row["categories"])
            except json.JSONDecodeError:
                categories = []

        embedding = None
        if row["embedding"]:
            try:
                embedding = pickle.loads(row["embedding"])
            except Exception:
                embedding = None

        return {
            "slug": row["slug"],
            "version": row["version"],
            "owner_id": row["owner_id"],
            "published_at": row["published_at"],
            "parent_version": row["parent_version"],
            "status": row["status"],
            "name": row["name"],
            "description": row["description"],
            "categories": categories,
            "complexity": row["complexity"],
            "source_type": row["source_type"],
            "embedding": embedding,
            "local_path": row["local_path"],
        }

    # ============ Categories ============

    def save_category(self, name: str, description: str = "") -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO categories (name, description) VALUES (?, ?)",
                (name, description)
            )
            return cursor.lastrowid

    def get_all_categories(self) -> List[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM categories ORDER BY name")
            return [dict(row) for row in cursor.fetchall()]

    # ============ Dashboard queries ============

    def search_skills_by_text(
        self,
        q: str = "",
        source: str = "",
        category: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[dict], int]:
        """Text search across internal skills and catalog_skills."""
        results = []
        total = 0

        with self._get_connection() as conn:
            cursor = conn.cursor()

            if source != "catalog":
                conds = ["status = 'active'"]
                params: list = []
                if q:
                    conds.append("(name LIKE ? OR description LIKE ?)")
                    like = f"%{q}%"
                    params.extend([like, like])
                if category:
                    conds.append("categories LIKE ?")
                    params.append(f"%{category}%")
                where = " AND ".join(conds)
                cursor.execute(f"SELECT COUNT(*) FROM skills WHERE {where}", params)
                cnt = cursor.fetchone()[0]
                total += cnt
                if source != "catalog":
                    cursor.execute(
                        f"""SELECT slug, version, name, description, categories,
                                   source_type, created_at
                            FROM skills WHERE {where}
                            ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                        params + [limit, offset],
                    )
                    for r in cursor.fetchall():
                        cats = []
                        try:
                            cats = json.loads(r["categories"]) if r["categories"] else []
                        except (json.JSONDecodeError, TypeError):
                            pass
                        results.append({
                            "id": r["slug"],
                            "name": r["name"],
                            "description": r["description"] or "",
                            "categories": cats,
                            "source": "internal",
                            "source_type": r["source_type"] or "",
                            "created_at": r["created_at"],
                        })

            if source != "internal":
                conds_c = ["1=1"]
                params_c: list = []
                if q:
                    conds_c.append("(display_name LIKE ? OR description LIKE ? OR description_en LIKE ?)")
                    like = f"%{q}%"
                    params_c.extend([like, like, like])
                if category:
                    conds_c.append("category_name LIKE ?")
                    params_c.append(f"%{category}%")
                where_c = " AND ".join(conds_c)
                cursor.execute(f"SELECT COUNT(*) FROM catalog_skills WHERE {where_c}", params_c)
                cnt_c = cursor.fetchone()[0]
                total += cnt_c

                remaining = limit - len(results)
                if remaining > 0 and source != "internal":
                    adj_offset = max(0, offset - (total - cnt_c)) if source == "" else offset
                    cursor.execute(
                        f"""SELECT full_name, name, display_name, description,
                                   description_en, category_name, owner, created_at
                            FROM catalog_skills WHERE {where_c}
                            ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                        params_c + [remaining, max(0, adj_offset)],
                    )
                    for r in cursor.fetchall():
                        results.append({
                            "id": r["full_name"],
                            "name": r["display_name"] or r["name"],
                            "description": r["description_en"] or r["description"] or "",
                            "categories": [r["category_name"]] if r["category_name"] else [],
                            "source": "catalog",
                            "source_type": "modelscope",
                            "created_at": r["created_at"],
                        })

        return results, total
