# Copyright (c) ModelScope Contributors. All rights reserved.
import logging
from pathlib import Path
from typing import List, Optional

from ..config import UltronConfig, default_config
from ..core.llm_service import LLMService
from .memory.memory_service import MemoryService

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".txt", ".md", ".log", ".json", ".yaml", ".yml",
    ".py", ".js", ".ts", ".java", ".go", ".rs", ".c", ".cpp", ".h",
    ".sh", ".bash", ".zsh", ".fish",
    ".toml", ".cfg", ".ini", ".conf",
    ".csv",
}

MAX_FILE_SIZE = 10_000_000  # 10MB


class SmartIngestionService:
    """
    Unified LLM-driven content ingestion service.

    Accepts file/directory paths or raw text, auto-dispatches by file type:
    - ``.jsonl`` session files are delegated to ConversationExtractor
      (incremental progress tracking).
    - Other supported files go through the LLM memory extraction pipeline.

    When ``archive_raw_uploads`` is enabled, each file payload is stored in
    ``raw_user_uploads`` before processing (same size cap as ingestion reads).

    Skill generation is handled internally by MemoryService when a memory
    reaches confirmed status.
    """

    def __init__(
        self,
        memory_service: MemoryService,
        llm_service: LLMService,
        config: Optional[UltronConfig] = None,
        conversation_extractor=None,
        database=None,
        llm_orchestrator=None,
    ):
        self.memory_service = memory_service
        self.llm = llm_service
        self.llm_orchestrator = llm_orchestrator
        self.config = config or default_config
        self.conversation_extractor = conversation_extractor
        self.db = database

    def ingest(self, paths: List[str], agent_id: str = "") -> dict:
        """
        Unified ingestion entry point.

        Accepts a list of file or directory paths. Directories are expanded
        recursively to nested regular files (hidden path segments skipped).
        Each file is dispatched by extension:
        ``.jsonl`` → ConversationExtractor, others → LLM text extraction.
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
                total_memories += r.get("memories_uploaded", 0) or r.get("total_uploaded", 0)

        return {
            "total_files": len(expanded),
            "successful": successful,
            "total_memories": total_memories,
            "results": results,
        }

    def _ingest_single(self, file_path: str, agent_id: str = "") -> dict:
        """Dispatch a single file by extension."""
        self._archive_file(file_path)
        p = Path(file_path)
        if p.suffix.lower() == ".jsonl":
            return self._ingest_jsonl(file_path, agent_id=agent_id)
        return self._ingest_regular(file_path)

    def _archive_file(self, file_path: str) -> None:
        """Archive raw file bytes to raw_user_uploads for disaster recovery."""
        if not self.db or not self.config.archive_raw_uploads:
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
        if not self.db or not self.config.archive_raw_uploads:
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
        """Delegate .jsonl session files to ConversationExtractor."""
        if not self.conversation_extractor:
            return self._error_result(
                "ConversationExtractor not configured", file_path=file_path,
            )
        return self.conversation_extractor.extract_from_session_file(
            session_file=file_path,
            agent_id=agent_id,
        )

    def _ingest_regular(self, file_path: str) -> dict:
        """Read a non-jsonl file and extract memories via LLM."""
        content = self._read_file(file_path)
        if content is None:
            return self._error_result(f"Cannot read file: {file_path}", file_path=file_path)
        return self.ingest_text(text=content, source_file=file_path)

    @staticmethod
    def _expand_paths(paths: List[str]) -> List[str]:
        """Expand directories to all nested regular files; keep plain files as-is."""
        expanded: List[str] = []
        for p_str in paths:
            p = Path(p_str)
            if p.is_dir():
                for f in sorted(p.rglob("*")):
                    if not f.is_file() or f.is_symlink():
                        continue
                    try:
                        rel_parts = f.relative_to(p).parts
                    except ValueError:
                        continue
                    if any(part.startswith(".") for part in rel_parts):
                        continue
                    expanded.append(str(f))
            elif p.is_file():
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

    def _read_file(self, file_path: str) -> Optional[str]:
        """Read file content with size and extension checks."""
        path = Path(file_path)

        if not path.is_file():
            logger.warning("Not a file or not found: %s", file_path)
            return None

        size = path.stat().st_size
        if size > MAX_FILE_SIZE:
            logger.warning("File too large (%d bytes): %s", size, file_path)
            return None

        suffix = path.suffix.lower()
        if suffix and suffix not in SUPPORTED_EXTENSIONS:
            logger.warning("Unsupported file type %s: %s", suffix, file_path)

        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning("Failed to read file: %s", e)
            return None

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
