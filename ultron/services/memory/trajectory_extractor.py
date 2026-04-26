# Copyright (c) ModelScope Contributors. All rights reserved.
"""Memory Hub bridge: token-windowed extraction from qualified trajectory segments."""
from __future__ import annotations

import logging
from typing import List, Optional

from ...config import UltronConfig, default_config
from ...core.database import Database
from ...services.memory.memory_service import MemoryService
from ...utils.llm_orchestrator import LLMOrchestrator
from ...utils.token_budget import split_messages_into_token_windows
from ...services.trajectory.quality_json import parse_segment_quality_json
from ...services.trajectory.session_reader import TrajectorySessionReader

logger = logging.getLogger(__name__)


class TrajectoryMemoryExtractor:
    """Loads eligible segments, runs LLM extraction, uploads to ``MemoryService``."""

    def __init__(
        self,
        db: Database,
        llm_orchestrator: LLMOrchestrator,
        memory_service: MemoryService,
        session_reader: TrajectorySessionReader,
        config: Optional[UltronConfig] = None,
    ):
        self.db = db
        self.llm_orchestrator = llm_orchestrator
        self.memory_service = memory_service
        self._reader = session_reader
        self.config = config or default_config

    def extract_memories_from_segments(self, batch_size: int = 50) -> dict:
        window_tokens = max(
            256,
            int(getattr(self.config, "conversation_extract_window_tokens", 65536)),
        )
        if not self.memory_service:
            logger.warning("MemoryService missing; skip segment extraction")
            return {"extracted": 0, "segments_processed": 0}
        if not self.llm_orchestrator or not self.llm_orchestrator.llm.is_available:
            logger.warning("LLM unavailable; skip segment extraction")
            return {"extracted": 0, "segments_processed": 0}

        memory_threshold = float(
            getattr(self.config, "trajectory_memory_score_threshold", 0.7)
        )
        try:
            from ms_agent.trajectory import is_memory_eligible
        except Exception as e:
            logger.warning("ms-agent trajectory eligibility unavailable: %s", e)
            return {"extracted": 0, "segments_processed": 0}

        coarse_segments = self.db.get_memory_eligible_unextracted_segments(
            batch_size,
            min_quality_score=memory_threshold,
        )
        segments = [
            seg
            for seg in coarse_segments
            if is_memory_eligible(
                parse_segment_quality_json(seg),
                threshold=memory_threshold,
            )
        ]
        memories_uploaded = 0
        segments_processed = 0

        for seg in segments:
            messages = self._reader.read_segment_messages(seg)
            if not messages:
                self.db.mark_segment_memory_extracted(seg["id"])
                segments_processed += 1
                continue

            base_tags = [
                "trajectory",
                f"type:{seg.get('task_type') or 'other'}",
                f"segment:{seg['id'][:8]}",
            ]
            topic = seg.get("topic") or ""
            if topic:
                base_tags.append(f"topic:{topic[:40]}")
            agent_id = seg.get("agent_id") or ""
            if agent_id:
                base_tags.append(f"agent:{agent_id}")

            try:
                n_up = self._windowed_extract_and_upload(
                    messages, window_tokens, base_tags
                )
                memories_uploaded += n_up
            except Exception as e:
                logger.warning(
                    "Segment memory extraction failed for %s: %s",
                    seg["id"][:8],
                    e,
                )
                continue

            self.db.mark_segment_memory_extracted(seg["id"])
            segments_processed += 1

        return {
            "extracted": memories_uploaded,
            "segments_processed": segments_processed,
        }

    def _windowed_extract_and_upload(
        self,
        messages: List[dict],
        window_tokens: int,
        base_tags: List[str],
    ) -> int:
        chunks = split_messages_into_token_windows(
            messages,
            window_tokens,
            self.llm_orchestrator.llm._count_tokens,
        )
        n = 0
        for chunk in chunks:
            combined = self.llm_orchestrator.prepare_conversation_text_for_memory_extraction(
                chunk,
                max_conversation_tokens=window_tokens,
            )
            if not combined.strip():
                continue
            extracted = self.llm_orchestrator.extract_memories_from_text(combined)
            for mem in extracted or []:
                content = (mem or {}).get("content") or ""
                if not content.strip():
                    continue
                try:
                    tags = list(base_tags) + list((mem or {}).get("tags") or [])
                    self.memory_service.upload_memory(
                        content=content,
                        context=(mem or {}).get("context", ""),
                        resolution=(mem or {}).get("resolution", ""),
                        tags=tags,
                    )
                    n += 1
                except Exception as e:
                    logger.warning("Failed to upload extracted memory: %s", e)
        return n
