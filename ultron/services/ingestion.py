# Copyright (c) ModelScope Contributors. All rights reserved.
import logging
from pathlib import Path
from typing import List, Optional

from ..config import UltronConfig, default_config
from ..core.llm_service import LLMService
from .memory.memory_service import MemoryService

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 10_000_000  # 10MB


class IngestionService:
    """
    Ingestion orchestration service.

    Accepts ``.jsonl`` paths or raw text. Path-based ``ingest`` only processes
    ``.jsonl`` session files (require ``trajectory_service``); user/assistant
    pairs are written to ``trajectory_records`` (labeled=0). Use
    ``ingest_text`` for non-jsonl content.

    When a database is configured, each file payload is stored in
    ``raw_user_uploads`` before processing (same size cap as ingestion reads).

    """

    def __init__(
        self,
        memory_service: MemoryService,
        llm_service: LLMService,
        config: Optional[UltronConfig] = None,
        database=None,
        llm_orchestrator=None,
        trajectory_service=None,
    ):
        self.memory_service = memory_service
        self.llm = llm_service
        self.llm_orchestrator = llm_orchestrator
        self.config = config or default_config
        self.db = database
        self.trajectory_service = trajectory_service

    def ingest(self, paths: List[str], agent_id: str = "") -> dict:
        """
        Unified ingestion entry point.

        Accepts a list of file or directory paths. Directories are expanded
        recursively to nested regular files (hidden path segments skipped).
        Only ``.jsonl`` files are collected (directories recurse; other extensions
        are skipped). Each file: trajectory ingest (requires ``trajectory_service``).
        """
        expanded = self._expand_paths(paths)
        if not expanded:
            return {
                "total_files": 0,
                "successful": 0,
                "total_memories": 0,
                "results": [],
            }

        results = []
        total_memories = 0
        successful = 0

        for file_path in expanded:
            r = self._ingest_single(file_path, agent_id=agent_id)
            results.append(r)
            if r.get("success"):
                successful += 1
                total_memories += (
                    r.get("memories_uploaded", 0)
                    or r.get("total_uploaded", 0)
                    or r.get("new_trajectory_count", 0)
                )

        return {
            "total_files": len(expanded),
            "successful": successful,
            "total_memories": total_memories,
            "results": results,
        }

    def _ingest_single(self, file_path: str, agent_id: str = "") -> dict:
        """Archive and ingest a single ``.jsonl`` session file."""
        p = Path(file_path)
        if p.suffix.lower() != ".jsonl":
            return self._error_result(
                "ingest only supports .jsonl files; use ingest_text for raw text",
                file_path=file_path,
            )
        self._archive_file(file_path)
        return self._ingest_jsonl(file_path, agent_id=agent_id)

    def _archive_file(self, file_path: str) -> None:
        """Archive raw file bytes to raw_user_uploads for disaster recovery."""
        if not self.db:
            return
        try:
            path = Path(file_path)
            if not path.is_file():
                return
            size = path.stat().st_size
            if size > MAX_FILE_SIZE:
                return
            payload = path.read_bytes()
            self.db.save_raw_user_upload(
                source="ingest_file",
                payload_blob=payload,
                meta={"file_path": file_path, "size": len(payload)},
            )
        except Exception as e:
            logger.warning("Failed to archive file %s: %s", file_path, e)

    def _archive_ingest_text_only(
        self,
        text: str,
        source_file: str,
    ) -> None:
        """
        Store UTF-8 bytes for standalone ``ingest_text`` (no ``source_file``).

        When ``source_file`` is set, bytes were already archived in ``_archive_file``.
        """
        if not self.db:
            return
        if source_file:
            return
        try:
            blob = text.encode("utf-8")
            if len(blob) > MAX_FILE_SIZE:
                logger.warning("ingest_text archive skipped (payload too large)")
                return
            self.db.save_raw_user_upload(
                source="ingest_text",
                payload_blob=blob,
            )
        except Exception as e:
            logger.warning("ingest_text archive failed: %s", e)

    def _ingest_jsonl(self, file_path: str, agent_id: str = "") -> dict:
        """Write .jsonl user/assistant pairs to trajectory_records (incremental by line)."""
        if self.trajectory_service is None:
            return self._error_result(
                "TrajectoryService is required for .jsonl ingestion",
                file_path=file_path,
            )
        return self._ingest_jsonl_trajectories(file_path, agent_id=agent_id)

    def _ingest_jsonl_trajectories(self, file_path: str, agent_id: str = "") -> dict:
        """Parse .jsonl and persist session-level trajectory row.

        Task segmentation is deferred to the periodic decay loop so that
        LLM unavailability at ingest time does not create incomplete
        fallback segments.
        """
        path = Path(file_path)
        result = {
            "success": False,
            "session_file": file_path,
            "new_trajectory_count": 0,
            "file_path": file_path,
            "error": None,
        }
        if not path.is_file():
            result["error"] = f"Not a file: {file_path}"
            return result
        size = path.stat().st_size
        if size > MAX_FILE_SIZE:
            result["error"] = f"File too large: {file_path}"
            return result
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except Exception as e:
            result["error"] = f"Cannot read file: {e}"
            return result
        all_lines = text.split("\n") if text else []

        # Save one session-level row (idempotent metadata for segmentation).
        is_new = False
        try:
            existing = self.trajectory_service.db.get_session_row(agent_id, file_path)
            if not existing:
                self.trajectory_service.record_session(
                    session_file=file_path,
                    source_agent_id=agent_id,
                )
                is_new = True
        except Exception as e:
            logger.warning("Failed to save session trajectory row: %s", e)

        if self.db:
            self.db.update_session_extract_progress(agent_id, file_path, len(all_lines))

        result["success"] = True
        result["new_trajectory_count"] = 1 if is_new else 0
        result["error"] = None
        return result

    @staticmethod
    def _expand_paths(paths: List[str]) -> List[str]:
        """Expand directories to nested ``.jsonl`` files only; plain paths must be ``.jsonl``."""
        expanded: List[str] = []
        for p_str in paths:
            p = Path(p_str)
            if p.is_dir():
                for f in sorted(p.rglob("*")):
                    if not f.is_file() or f.is_symlink():
                        continue
                    if f.suffix.lower() != ".jsonl":
                        continue
                    try:
                        rel_parts = f.relative_to(p).parts
                    except ValueError:
                        continue
                    if any(part.startswith(".") for part in rel_parts):
                        continue
                    expanded.append(str(f))
            elif p.is_file():
                if p.suffix.lower() != ".jsonl":
                    logger.warning(
                        "Skipping non-jsonl file (ingest only supports .jsonl): %s",
                        p_str,
                    )
                    continue
                expanded.append(str(p))
            else:
                logger.warning("Path not found or not a file/directory: %s", p_str)
        return expanded

    def ingest_text(
        self,
        text: str,
        source_file: str = "",
    ) -> dict:
        """
        Ingest raw text: extract memories via LLM and upload them.

        Args:
            text: Raw text content.
            source_file: Optional source filename for tagging.
        """
        result = self._error_result(source_file=source_file)

        if not self.llm.is_available:
            result["error"] = "LLM unavailable (requires OpenAI-compatible API key)"
            return result

        if not text or not text.strip():
            result["error"] = "Empty input text"
            return result

        self._archive_ingest_text_only(text, source_file)

        try:
            extracted = self.llm_orchestrator.extract_memories_from_text(text)
        except Exception as e:
            result["error"] = f"LLM extraction failed: {e}"
            return result

        result["memories_extracted"] = len(extracted)
        if not extracted:
            result["error"] = "No memories extracted from text"
            return result

        uploaded = []
        for mem in extracted:
            content = mem.get("content", "")
            if not content:
                continue
            try:
                tags = list(mem.get("tags", []))
                if source_file:
                    tags.append(f"source:{Path(source_file).name}")

                record = self.memory_service.upload_memory(
                    content=content,
                    context=mem.get("context", ""),
                    resolution=mem.get("resolution", ""),
                    tags=tags,
                )
                uploaded.append(record.to_dict())
            except Exception as e:
                logger.warning("Failed to upload extracted memory: %s", e)

        result["memories_uploaded"] = len(uploaded)
        result["memories"] = uploaded
        result["success"] = len(uploaded) > 0
        return result

    @staticmethod
    def _error_result(error: str = None, **extra) -> dict:
        result = {
            "success": False,
            "memories_extracted": 0,
            "memories_uploaded": 0,
            "memories": [],
            "error": error,
        }
        result.update(extra)
        return result
