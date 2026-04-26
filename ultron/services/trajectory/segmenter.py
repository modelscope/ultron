# Copyright (c) ModelScope Contributors. All rights reserved.
"""LLM-based task segmentation over session messages."""
from __future__ import annotations

import logging
import uuid
from ...core.database import Database
from ...utils.jsonl_session_messages import parse_jsonl_lines_for_trajectory
from ...utils.llm_orchestrator import LLMOrchestrator
from ...utils.token_budget import compute_segment_fingerprint

from .session_reader import TrajectorySessionReader

logger = logging.getLogger(__name__)


class TrajectorySegmenter:
    """Loads unsegmented sessions, runs ``segment_conversation_tasks``, persists ``task_segments``."""

    def __init__(
        self,
        db: Database,
        llm_orchestrator: LLMOrchestrator,
        session_reader: TrajectorySessionReader,
    ):
        self.db = db
        self.llm_orchestrator = llm_orchestrator
        self._reader = session_reader

    def segment_pending_sessions(self, batch_size: int = 50) -> dict:
        rows = self.db.get_unsegmented_sessions(batch_size)
        segmented = 0
        skipped = 0

        for row in rows:
            session_file = row.get("session_file") or ""
            agent_id = row.get("source_agent_id") or ""
            if not session_file:
                skipped += 1
                continue

            all_lines = self._reader.read_session_lines(session_file)
            if all_lines is None:
                logger.warning("Session file missing for segmentation: %s", session_file)
                skipped += 1
                continue

            messages = parse_jsonl_lines_for_trajectory(all_lines)
            if not messages:
                self.db.mark_session_segmented(agent_id, session_file)
                segmented += 1
                continue

            result = self.llm_orchestrator.segment_conversation_tasks(messages)
            if result is None:
                skipped += 1
                continue

            if not result:
                self.db.mark_session_segmented(agent_id, session_file)
                segmented += 1
                continue

            existing_segments = self.db.get_segments_for_session(agent_id, session_file)
            existing_fps = {s["fingerprint"]: s for s in existing_segments}
            existing_by_index: dict = {}
            for s in existing_segments:
                existing_by_index.setdefault(s["segment_index"], []).append(s)

            for i, seg in enumerate(result):
                seg_messages = messages[seg["start"] - 1 : seg["end"]]
                fp = compute_segment_fingerprint(seg_messages)

                if fp in existing_fps:
                    continue

                for old in existing_by_index.get(i, []):
                    if old["fingerprint"] != fp:
                        old_tag = f"segment:{old['id'][:8]}"
                        self.db.archive_memories_by_tag(old_tag)
                        self.db.delete_segment(old["id"])
                        logger.info(
                            "Superseded segment %s (index=%d) in %s",
                            old["id"][:8],
                            i,
                            session_file,
                        )

                self.db.save_task_segment(
                    segment_id=str(uuid.uuid4()),
                    agent_id=agent_id,
                    session_file=session_file,
                    segment_index=i,
                    start_line=seg["start"],
                    end_line=seg["end"],
                    fingerprint=fp,
                    topic=seg.get("topic", ""),
                )

            self.db.mark_session_segmented(agent_id, session_file)
            segmented += 1

        return {"segmented": segmented, "skipped": skipped}
