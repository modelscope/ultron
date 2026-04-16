# Copyright (c) ModelScope Contributors. All rights reserved.
import json
from pathlib import Path
from typing import List, Optional, Tuple

from ...config import default_config
from ...core.models import MemoryRecord
from ...utils.token_budget import split_messages_into_token_windows


class ConversationExtractor:
    """
    Auto-extract reusable memories from conversations (requires LLMOrchestrator).
    """

    def __init__(self, memory_service=None, llm_orchestrator=None, database=None, config=None):
        """
        Args:
            memory_service: MemoryService instance
            llm_orchestrator: LLMOrchestrator instance (required for extraction)
            database: Database instance (for session extract progress tracking)
            config: UltronConfig (optional; overlap lines, sliding window token limit)
        """
        self.memory_service = memory_service
        self.llm_orchestrator = llm_orchestrator
        self.db = database
        self.config = config if config is not None else default_config
        k = int(getattr(self.config, "session_extract_overlap_lines", 5))
        w = int(getattr(self.config, "conversation_extract_window_tokens", 65536))
        self._overlap_lines = max(0, k)
        self._window_tokens = max(256, w)

    def _upload_extracted_memories(
        self,
        extracted: List[dict],
    ) -> List[MemoryRecord]:
        """Write LLM-returned memory list to MemoryService, skipping empty content."""
        out = []
        for mem in extracted or []:
            content = mem.get("content", "")
            if not content:
                continue
            out.append(
                self.memory_service.upload_memory(
                    content=content,
                    context=mem.get("context", ""),
                    resolution=mem.get("resolution", ""),
                    tags=list(mem.get("tags", [])),
                )
            )
        return out

    def _windowed_extract_to_records(
        self,
        messages: List[dict],
    ) -> Tuple[List[MemoryRecord], int, int]:
        """
        Split by ``conversation_extract_window_tokens``, then prepare + extract + upload per chunk.

        Returns:
            (memory_records, memories_extracted_sum, window_chunk_count)
        """
        chunks = split_messages_into_token_windows(
            messages,
            self._window_tokens,
            self.llm_orchestrator.llm._count_tokens,
        )
        all_records: List[MemoryRecord] = []
        memories_extracted = 0
        for chunk in chunks:
            combined_text = self.llm_orchestrator.prepare_conversation_text_for_memory_extraction(
                chunk,
                max_conversation_tokens=self._window_tokens,
            )
            extracted = self.llm_orchestrator.extract_memories_from_text(combined_text)
            extracted = extracted or []
            memories_extracted += len(extracted)
            all_records.extend(
                self._upload_extracted_memories(extracted)
            )
        return all_records, memories_extracted, len(chunks)

    def extract_from_session_path(
        self,
        session_path: str,
        min_confidence: float = 0.5,
    ) -> dict:
        """
        Incrementally extract memories from a session path.

        - Directory: scans all .jsonl files and processes each incrementally.
        - File: processes only that file.

        min_confidence is kept for backwards-compatibility but is currently unused (LLM extraction only).

        Returns:
            {"success": bool, "files_processed": N, "total_new_lines": N,
             "total_extracted": N, "total_uploaded": N, "details": [...]}
        """
        _ = min_confidence
        path = Path(session_path)

        if path.is_dir():
            jsonl_files = sorted(path.glob("*.jsonl"))
        elif path.is_file() and path.suffix == ".jsonl":
            jsonl_files = [path]
        else:
            return {"success": False, "error": f"Invalid path (must be a .jsonl file or directory containing .jsonl files): {session_path}"}

        if not jsonl_files:
            return {"success": True, "files_processed": 0, "total_new_lines": 0,
                    "total_extracted": 0, "total_uploaded": 0, "details": []}

        details = []
        total_new = 0
        total_extracted = 0
        total_uploaded = 0

        for f in jsonl_files:
            r = self.extract_from_session_file(
                session_file=str(f),
                min_confidence=min_confidence,
            )
            details.append({"file": f.name, **r})
            total_new += r.get("new_lines", 0)
            total_extracted += r.get("memories_extracted", 0)
            total_uploaded += r.get("memories_uploaded", 0)

        return {
            "success": True,
            "files_processed": len(jsonl_files),
            "total_new_lines": total_new,
            "total_extracted": total_extracted,
            "total_uploaded": total_uploaded,
            "details": details,
        }

    def extract_from_session_file(
        self,
        session_file: str,
        min_confidence: float = 0.5,
        agent_id: str = "",
    ) -> dict:
        """
        Incrementally extract memories from a session .jsonl file.

        The server tracks processed line count per ``agent_id:session_file``.
        Only new lines are processed each run; the LLM receives
        ``all_lines[max(0, last_processed - K):last_processed]`` as context
        prepended to the new lines (K defaults to 5, see config).

        min_confidence is kept for backwards-compatibility but is currently unused.

        Returns:
            {"success": bool, "new_lines": N, "overlap_lines": N, "extract_window_chunks": N,
             "memories_extracted": N, "memories_uploaded": N,              "memories": [...], "error": str|None}
        """
        _ = min_confidence
        result = {
            "success": False,
            "session_file": session_file,
            "new_lines": 0,
            "overlap_lines": 0,
            "extract_window_chunks": 0,
            "memories_extracted": 0,
            "memories_uploaded": 0,
            "memories": [],
            "error": None,
        }

        all_lines = self._read_session_lines(session_file)
        if all_lines is None:
            result["error"] = f"Cannot read session file: {session_file}"
            return result

        total_lines = len(all_lines)

        last_processed = 0
        if self.db:
            last_processed = self.db.get_session_extract_progress(agent_id, session_file)

        if total_lines <= last_processed:
            result["success"] = True
            result["error"] = None
            return result

        new_lines = all_lines[last_processed:]
        result["new_lines"] = len(new_lines)

        overlap_start = max(0, last_processed - self._overlap_lines)
        overlap_slice = all_lines[overlap_start:last_processed]
        result["overlap_lines"] = len(overlap_slice)
        lines_for_llm = overlap_slice + new_lines

        messages = self._parse_lines_to_messages(lines_for_llm)
        if not messages:
            if self.db:
                self.db.update_session_extract_progress(agent_id, session_file, total_lines)
            result["success"] = True
            return result

        if not self.memory_service:
            result["error"] = "MemoryService not configured"
            return result

        if not self.llm_orchestrator or not self.llm_orchestrator.llm.is_available:
            result["error"] = "LLM unavailable: configure an OpenAI-compatible API key"
            return result

        try:
            records, memories_extracted, n_chunks = self._windowed_extract_to_records(
                messages
            )
        except Exception as e:
            result["error"] = f"LLM extraction failed: {e}"
            return result

        uploaded = [r.to_dict() for r in records]

        result["extract_window_chunks"] = n_chunks
        result["memories_extracted"] = memories_extracted
        result["memories_uploaded"] = len(uploaded)
        result["memories"] = uploaded
        result["success"] = len(uploaded) > 0
        result["error"] = None if result["success"] else "No extractable memories found"

        if self.db:
            self.db.update_session_extract_progress(agent_id, session_file, total_lines)

        return result

    def _read_session_lines(self, file_path: str) -> Optional[List[str]]:
        """Read all lines from a session file (raw strings)."""
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            return None
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            return text.split("\n") if text else []
        except Exception:
            return None

    def _parse_lines_to_messages(self, lines: List[str]) -> List[dict]:
        """Parse jsonl lines into a message list (user/assistant only)."""
        messages = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("_type") == "metadata":
                continue
            role = obj.get("role", "")
            content = obj.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        return messages
