# Copyright (c) ModelScope Contributors. All rights reserved.
"""ms-agent trajectory metric labeling for task segments."""
from __future__ import annotations

import json
import logging

from ...core.database import Database
from ...utils.llm_orchestrator import LLMOrchestrator

from .session_reader import TrajectorySessionReader

logger = logging.getLogger(__name__)


class TrajectoryLabeler:
    """Runs ``analyze_trajectory`` on unlabeled segments and writes DB metrics."""

    def __init__(
        self,
        db: Database,
        llm_orchestrator: LLMOrchestrator,
        session_reader: TrajectorySessionReader,
    ):
        self.db = db
        self.llm_orchestrator = llm_orchestrator
        self._reader = session_reader

    def label_pending_segments(self, batch_size: int = 50) -> dict:
        try:
            from ms_agent.trajectory import analyze_trajectory
        except Exception as e:
            logger.warning("ms-agent trajectory analyzer unavailable: %s", e)
            return {"labeled": 0, "skipped": len(self.db.get_unlabeled_segments(batch_size))}

        segments = self.db.get_unlabeled_segments(batch_size)
        labeled = 0
        skipped = 0
        metric_llm = getattr(self.llm_orchestrator, "quality_llm", None)
        if not metric_llm or not getattr(metric_llm, "is_available", False):
            return {"labeled": 0, "skipped": len(segments)}
        for seg in segments:
            messages = self._reader.read_segment_messages(seg)
            if not messages:
                skipped += 1
                continue
            try:
                assessment = analyze_trajectory(
                    messages,
                    success=True,
                    topic=seg.get("topic", ""),
                    metric_llm=metric_llm,
                    require_model=True,
                )
            except Exception as e:
                logger.warning(
                    "Trajectory metric analysis failed for segment %s: %s",
                    str(seg.get("id", ""))[:8],
                    e,
                )
                skipped += 1
                continue
            self.db.update_segment_metrics(
                seg["id"],
                json.dumps(assessment, ensure_ascii=False),
            )
            labeled += 1
        return {"labeled": labeled, "skipped": skipped}
