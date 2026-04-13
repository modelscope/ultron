# Copyright (c) ModelScope Contributors. All rights reserved.
import json
import pickle
from typing import List, Optional, Tuple


class _CatalogSkillMixin:
    """External skill catalog (ModelScope Skill Hub) database operations."""

    def bulk_upsert_catalog_skills(self, skills: List[dict]) -> int:
        """Batch insert/update catalog skills. Returns count of rows affected."""
        if not skills:
            return 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            count = 0
            for s in skills:
                embedding_blob = None
                if s.get("embedding"):
                    embedding_blob = pickle.dumps(s["embedding"])
                cursor.execute("""
                    INSERT OR REPLACE INTO catalog_skills (
                        full_name, name, display_name, path,
                        description, description_en, owner,
                        category_id, category_name, embedding
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    s["full_name"],
                    s.get("name", ""),
                    s.get("display_name", ""),
                    s.get("path", ""),
                    s.get("description", ""),
                    s.get("description_en", ""),
                    s.get("owner", ""),
                    s.get("category_id", ""),
                    s.get("category_name", ""),
                    embedding_blob,
                ))
                count += cursor.rowcount
            return count

    def get_catalog_skills_with_embeddings(self) -> List[Tuple[dict, List[float]]]:
        """Return all catalog skills that have embeddings, for cosine search."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM catalog_skills WHERE embedding IS NOT NULL")
            results = []
            for row in cursor.fetchall():
                skill_dict = self._catalog_row_to_dict(row)
                embedding = pickle.loads(row["embedding"]) if row["embedding"] else []
                results.append((skill_dict, embedding))
            return results

    def get_catalog_skill(self, full_name: str) -> Optional[dict]:
        """Look up a single catalog skill by full_name."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM catalog_skills WHERE full_name = ?", (full_name,))
            row = cursor.fetchone()
            return self._catalog_row_to_dict(row) if row else None

    def get_catalog_stats(self) -> dict:
        """Return catalog skill counts."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM catalog_skills")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM catalog_skills WHERE embedding IS NOT NULL")
            with_embedding = cursor.fetchone()[0]
            cursor.execute("""
                SELECT category_id, category_name, COUNT(*) as cnt
                FROM catalog_skills
                WHERE category_id IS NOT NULL AND category_id != ''
                GROUP BY category_id
                ORDER BY cnt DESC
            """)
            categories = [
                {"id": r["category_id"], "name": r["category_name"], "count": r["cnt"]}
                for r in cursor.fetchall()
            ]
            return {
                "total": total,
                "with_embedding": with_embedding,
                "categories": categories,
            }

    @staticmethod
    def _catalog_row_to_dict(row) -> dict:
        return {
            "id": row["id"],
            "full_name": row["full_name"],
            "name": row["name"],
            "display_name": row["display_name"],
            "path": row["path"],
            "description": row["description"],
            "description_en": row["description_en"],
            "owner": row["owner"],
            "category_id": row["category_id"],
            "category_name": row["category_name"],
            "created_at": row["created_at"],
        }
