# Copyright (c) ModelScope Contributors. All rights reserved.
"""SFT sample export: Twinkle/Qwen chat-template formatting, no trajectory hub coupling."""
from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

from ...config import UltronConfig, default_config
from ...core.database import Database
from ...services.trajectory.quality_json import parse_segment_quality_json
from ...services.trajectory.session_reader import TrajectorySessionReader

logger = logging.getLogger(__name__)


def render_tool_calls_qwen3(tool_calls: list) -> str:
    """Pre-render OpenAI-style tool_calls into Qwen3.5 chat-template format."""
    parts: list[str] = []
    for tc in tool_calls:
        func = tc.get("function") or {}
        name = func.get("name", "")
        raw_args = func.get("arguments", "{}")
        if isinstance(raw_args, str):
            try:
                args_dict = json.loads(raw_args)
            except (ValueError, TypeError):
                args_dict = {"_raw": raw_args}
        else:
            args_dict = raw_args

        params = ""
        if isinstance(args_dict, dict):
            for k, v in args_dict.items():
                v_str = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
                params += f"<parameter={k}>\n{v_str}\n</parameter>\n"

        parts.append(f"<tool_call>\n<function={name}>\n{params}</function>\n</tool_call>")
    return "\n".join(parts)


def convert_message_to_twinkle(msg: dict) -> dict:
    """Native message dict to twinkle/HF-safe format (tool_calls pre-rendered into content)."""
    role = msg.get("role", "")
    content = msg.get("content", "") or ""
    out: dict = {"role": role, "content": content}

    if role == "assistant":
        raw_tc = msg.get("tool_calls")
        if raw_tc:
            rendered = render_tool_calls_qwen3(raw_tc)
            if content.strip():
                out["content"] = content + "\n\n" + rendered
            else:
                out["content"] = rendered
        rc = msg.get("reasoning_content", "")
        if rc:
            out["reasoning_content"] = rc

    return out


class SFTExporter:
    """Builds SFT training rows from DB-eligible task segments."""

    def __init__(
        self,
        db: Database,
        session_reader: TrajectorySessionReader,
        config: Optional[UltronConfig] = None,
    ):
        self.db = db
        self._reader = session_reader
        self.config = config or default_config

    def export_sft(
        self,
        task_type: Optional[str] = None,
        min_quality_score: Optional[float] = None,
        limit: int = 5000,
    ) -> List[dict[str, Any]]:
        out: List[dict[str, Any]] = []
        sft_threshold = float(
            min_quality_score
            if min_quality_score is not None
            else getattr(self.config, "trajectory_sft_score_threshold", 0.8)
        )
        try:
            from ms_agent.trajectory import is_sft_eligible
        except Exception as e:
            logger.warning("ms-agent trajectory eligibility unavailable: %s", e)
            return out

        candidate_segs = self.db.get_segments_for_sft(
            task_type=task_type,
            limit=limit,
            min_quality_score=sft_threshold,
        )
        for seg in candidate_segs:
            if not is_sft_eligible(
                parse_segment_quality_json(seg),
                threshold=sft_threshold,
            ):
                continue
            messages = self._reader.read_segment_messages(seg)
            if len(messages) < 2:
                continue
            out.append({
                "messages": [convert_message_to_twinkle(m) for m in messages],
                "topic": seg.get("topic", ""),
            })
            if len(out) >= limit:
                break
        return out

    def export_sft_since(
        self,
        since: Optional[str] = None,
        limit: int = 5000,
    ) -> List[dict[str, Any]]:
        sft_threshold = float(
            getattr(self.config, "trajectory_sft_score_threshold", 0.8)
        )
        segments = self.db.get_segments_for_sft_since(
            since=since,
            limit=limit,
            min_quality_score=sft_threshold,
        )
        out: List[dict[str, Any]] = []
        try:
            from ms_agent.trajectory import is_sft_eligible
        except Exception as e:
            logger.warning("ms-agent trajectory eligibility unavailable: %s", e)
            return out
        for seg in segments:
            if not is_sft_eligible(
                parse_segment_quality_json(seg),
                threshold=sft_threshold,
            ):
                continue
            messages = self._reader.read_segment_messages(seg)
            if len(messages) < 2:
                continue
            out.append({
                "messages": [convert_message_to_twinkle(m) for m in messages],
                "topic": seg.get("topic", ""),
            })
        return out
