# Copyright (c) ModelScope Contributors. All rights reserved.
"""Local session file access and JSONL parsing for trajectory pipelines."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from ...utils.jsonl_session_messages import parse_jsonl_lines_for_trajectory

logger = logging.getLogger(__name__)


class TrajectorySessionReader:
    """Reads session lines and segment message slices from disk-backed ``.jsonl``."""

    def read_session_lines(self, file_path: str) -> Optional[List[str]]:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            return None
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            return text.split("\n") if text else []
        except Exception:
            return None

    def read_segment_messages(self, seg: dict) -> List[dict]:
        """Read messages for a task segment from its session file (1-based line range)."""
        session_file = seg.get("session_file") or ""
        start = int(seg.get("start_line", 1))
        end = int(seg.get("end_line", 0))
        if not session_file or end < start:
            return []
        all_lines = self.read_session_lines(session_file)
        if not all_lines:
            return []
        all_messages = parse_jsonl_lines_for_trajectory(all_lines)
        return all_messages[start - 1 : end]
