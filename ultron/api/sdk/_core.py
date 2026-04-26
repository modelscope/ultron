# Copyright (c) ModelScope Contributors. All rights reserved.
import logging
from pathlib import Path
from typing import List, Optional

from ...services.ingestion import MAX_FILE_SIZE

logger = logging.getLogger(__name__)


class CoreMixin:
    def _archive_skill_tree(self, skill_dir: str) -> None:
        """
        Persist each regular file under ``skill_dir`` into ``raw_user_uploads`` (raw bytes).
        """
        if not self.db:
            return
        root = Path(skill_dir).resolve()
        if not root.is_dir():
            return
        try:
            for f in root.rglob("*"):
                if not f.is_file() or f.is_symlink():
                    continue
                try:
                    rel = str(f.relative_to(root))
                except ValueError:
                    continue
                if any(part.startswith(".") for part in Path(rel).parts):
                    continue
                try:
                    sz = f.stat().st_size
                    if sz > MAX_FILE_SIZE:
                        continue
                    payload = f.read_bytes()
                    self.db.save_raw_user_upload(
                        source="skill_upload_file",
                        payload_blob=payload,
                        meta={"rel_path": rel, "skill_root": str(root)},
                    )
                except OSError as e:
                    logger.warning("Skill file archive skip %s: %s", f, e)
        except OSError as e:
            logger.warning("Skill tree archive failed for %s: %s", skill_dir, e)

    def get_raw_user_upload(self, upload_id: str) -> Optional[dict]:
        """Load a raw upload snapshot by id (includes ``payload_text`` / ``payload_base64``)."""
        return self.db.get_raw_user_upload(upload_id)

    def list_raw_user_uploads(
        self,
        limit: int = 100,
        offset: int = 0,
        source_prefix: Optional[str] = None,
    ) -> List[dict]:
        """List archive summaries without full payload bodies."""
        return self.db.list_raw_user_uploads(limit, offset, source_prefix)

    def _increment_version(self, version: str) -> str:
        """Bump the last numeric segment of a dotted version string."""
        try:
            parts = version.split(".")
            parts[-1] = str(int(parts[-1]) + 1)
            return ".".join(parts)
        except Exception:
            return "1.0.1"

    def get_stats(self) -> dict:
        """Return aggregate counters for storage, categories, embedding, and memory."""
        storage_stats = self.storage.get_storage_stats()
        category_stats = self.catalog.get_category_statistics()
        embedding_info = self.embedding.get_model_info()
        memory_stats = self.memory_service.get_memory_stats()

        return {
            "storage": storage_stats,
            "categories": category_stats,
            "embedding": embedding_info,
            "memory": memory_stats,
        }

    def list_all_skills(self) -> List[dict]:
        """List metadata for all stored skills."""
        return self.storage.list_all_skills()

    def reset_all(self) -> dict:
        """
        Wipe database rows (memories, skill metadata, safety/error logs, usage, evolution,
        categories) and delete skill files under skills and archive directories.

        Call before switching embedding model or vector dimension to avoid mixing vectors.
        Also removes ``models_dir/embedding_profile.json`` so the next startup can bind a
        new embedding backend/model/dimension without a stale profile error.
        """
        db_stats = self.db.wipe_all_data()
        storage_stats = self.storage.clear_all_skill_files(include_archive=True)
        profile_file = self.config.models_dir / "embedding_profile.json"
        profile_removed = False
        if profile_file.is_file():
            try:
                profile_file.unlink()
                profile_removed = True
            except OSError as e:
                logger.warning("Could not remove embedding profile %s: %s", profile_file, e)
        return {
            "database": db_stats,
            "storage": storage_stats,
            "embedding_profile_removed": profile_removed,
        }
