# Copyright (c) ModelScope Contributors. All rights reserved.
from __future__ import annotations

import uuid
from typing import Any, List, Optional

from ...config import UltronConfig, default_config
from ...core.database import Database
from ...services.memory.memory_service import MemoryService
from ...services.memory.trajectory_extractor import TrajectoryMemoryExtractor
from ...services.training.sft_exporter import SFTExporter
from ...utils.llm_orchestrator import LLMOrchestrator

from .labeler import TrajectoryLabeler
from .segmenter import TrajectorySegmenter
from .session_reader import TrajectorySessionReader


class TrajectoryService:
    """Facade: session storage, segment/label/extract/SFT; delegates to collaborators."""

    def __init__(
        self,
        db: Database,
        llm_orchestrator: LLMOrchestrator,
        memory_service: MemoryService,
        config: Optional[UltronConfig] = None,
    ):
        self.db = db
        self.llm_orchestrator = llm_orchestrator
        self.memory_service = memory_service
        self.config = config or default_config

        self._session_reader = TrajectorySessionReader()
        self._segmenter = TrajectorySegmenter(
            self.db, self.llm_orchestrator, self._session_reader
        )
        self._labeler = TrajectoryLabeler(
            self.db, self.llm_orchestrator, self._session_reader
        )
        self._memory_extractor = TrajectoryMemoryExtractor(
            self.db,
            self.llm_orchestrator,
            self.memory_service,
            self._session_reader,
            config=self.config,
        )
        self._sft_exporter = SFTExporter(
            self.db, self._session_reader, config=self.config
        )

    @property
    def sft_exporter(self) -> SFTExporter:
        """Shared ``SFTExporter`` for training and SDK export APIs."""
        return self._sft_exporter

    def record_session(
        self,
        session_file: str,
        source_agent_id: str = "",
    ) -> str:
        """Persist one session-level row (pair_index=-1, labeled=0). Idempotent."""
        existing = self.db.get_session_row(source_agent_id, session_file)
        if existing:
            return existing["id"]
        tid = str(uuid.uuid4())
        self.db.save_session_trajectory(
            traj_id=tid,
            session_file=session_file,
            source_agent_id=source_agent_id,
        )
        return tid

    def segment_pending_sessions(self, batch_size: int = 50) -> dict:
        """Segment unsegmented sessions using LLM (see ``TrajectorySegmenter``)."""
        return self._segmenter.segment_pending_sessions(batch_size)

    def label_pending_segments(self, batch_size: int = 50) -> dict:
        return self._labeler.label_pending_segments(batch_size)

    def extract_memories_from_segments(self, batch_size: int = 50) -> dict:
        return self._memory_extractor.extract_memories_from_segments(batch_size)

    def export_sft(
        self,
        task_type: Optional[str] = None,
        min_quality_score: Optional[float] = None,
        limit: int = 5000,
    ) -> List[dict[str, Any]]:
        return self._sft_exporter.export_sft(
            task_type=task_type,
            min_quality_score=min_quality_score,
            limit=limit,
        )

    def export_sft_since(
        self,
        since: Optional[str] = None,
        limit: int = 5000,
    ) -> List[dict[str, Any]]:
        return self._sft_exporter.export_sft_since(since=since, limit=limit)

    def get_trajectory_stats(self) -> dict:
        stats = self.db.get_trajectory_stats()
        stats["segments"] = self.db.get_segment_stats()
        return stats
