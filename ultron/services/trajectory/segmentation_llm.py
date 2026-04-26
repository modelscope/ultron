# Copyright (c) ModelScope Contributors. All rights reserved.
"""LLM-driven conversation task segmentation."""
from __future__ import annotations

import logging
from typing import List, Optional

from ...core.llm_service import LLMService
from ...utils.jsonl_session_messages import message_body_for_llm
from ...utils.token_budget import truncate_text_to_token_limit

logger = logging.getLogger(__name__)

_TASK_SEGMENTATION_PROMPT = """You are a conversation analyst. The following is a multi-turn conversation between a user and an assistant.
Identify distinct task boundaries — a new task starts when the user shifts to a clearly different topic/goal.

Rules:
- Each segment should be a self-contained task (e.g., "write code for X", "debug Y", "explain Z")
- Minor follow-ups on the same topic belong to the same segment
- If the entire conversation is one task, return a single segment
- Use 1-based message indices referring to the numbered message sequence below
- Segments must be contiguous and non-overlapping, covering all messages
- "start" is the first message index, "end" is the last message index (both inclusive)

Return strictly as a JSON array with no other text:
```json
[
  {{"start": 1, "end": 5, "topic": "short task description"}},
  {{"start": 6, "end": 12, "topic": "short task description"}}
]
```

Conversation ({n_messages} messages):
{conversation_text}
"""


def _numbered_conversation_lines(messages_chunk: List[dict]) -> str:
    lines: List[str] = []
    for idx, msg in enumerate(messages_chunk, 1):
        role = msg.get("role", "")
        body = message_body_for_llm(msg)
        lines.append(f"[{idx}] [{role}]: {body}")
    return "\n".join(lines)


def _validate_local_segments(result: object, n: int) -> Optional[List[dict]]:
    if not isinstance(result, list) or not result:
        return None
    segments: List[dict] = []
    for seg in result:
        if not isinstance(seg, dict):
            return None
        start = int(seg.get("start", 0))
        end = int(seg.get("end", 0))
        topic = str(seg.get("topic", ""))
        if start < 1 or end < start or end > n:
            return None
        segments.append({"start": start, "end": end, "topic": topic})
    segments.sort(key=lambda s: s["start"])
    if segments[0]["start"] != 1 or segments[-1]["end"] != n:
        return None
    for i in range(1, len(segments)):
        if segments[i]["start"] != segments[i - 1]["end"] + 1:
            return None
    return segments


def segment_conversation_tasks_with_llm(
    llm: LLMService,
    messages: List[dict],
) -> Optional[List[dict]]:
    """Split a conversation into distinct task segments using LLM windows."""
    n = len(messages)
    if n == 0:
        return []
    if n <= 2:
        return [{"start": 1, "end": n, "topic": "full conversation"}]
    if not llm.is_available:
        return None

    def chunk_fits(start_0: int, end_0: int) -> bool:
        chunk = messages[start_0 : end_0 + 1]
        k = len(chunk)
        if k == 0:
            return False
        conv = _numbered_conversation_lines(chunk)
        shell = _TASK_SEGMENTATION_PROMPT.format(n_messages=k, conversation_text="")
        budget = llm.user_text_token_budget(shell)
        return llm._count_tokens(conv) <= budget

    def max_end_for_start(start_0: int) -> int:
        if not chunk_fits(start_0, start_0):
            return start_0
        lo, hi = start_0, n - 1
        best = start_0
        while lo <= hi:
            mid = (lo + hi) // 2
            if chunk_fits(start_0, mid):
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return best

    def call_llm_on_chunk(start_0: int, end_0: int) -> Optional[List[dict]]:
        chunk = messages[start_0 : end_0 + 1]
        k = len(chunk)
        conv = _numbered_conversation_lines(chunk)
        shell = _TASK_SEGMENTATION_PROMPT.format(n_messages=k, conversation_text="")
        budget = llm.user_text_token_budget(shell)
        if llm._count_tokens(conv) > budget:
            if k != 1:
                return None
            conv = truncate_text_to_token_limit(conv, budget, llm._count_tokens)
        prompt = _TASK_SEGMENTATION_PROMPT.format(
            n_messages=k, conversation_text=conv
        )
        try:
            response = llm.call(llm.dashscope_user_messages(prompt))
            if not response:
                return None
            result = llm.parse_json_response(response)
        except Exception:
            return None
        return _validate_local_segments(result, k)

    out: List[dict] = []
    i_at = 0
    first_call = True
    guard = 0
    while i_at < n:
        guard += 1
        if guard > n + 8:
            logger.error("segment_conversation_tasks: too many windows")
            return None
        end_0 = max_end_for_start(i_at)
        local_segs = call_llm_on_chunk(i_at, end_0)
        if not local_segs:
            return None
        global_segs: List[dict] = [
            {
                "start": i_at + s["start"],
                "end": i_at + s["end"],
                "topic": s["topic"],
            }
            for s in local_segs
        ]
        if not first_call and global_segs:
            trim_start = int(global_segs[0]["start"])
            while out and int(out[-1]["start"]) >= trim_start:
                out.pop()
        for gs in global_segs:
            out.append(dict(gs))
        first_call = False
        if end_0 >= n - 1:
            break
        if len(global_segs) == 1:
            i_next = end_0 + 1
        else:
            i_next = int(global_segs[-1]["start"]) - 1
        if i_next <= i_at:
            logger.warning(
                "segment_conversation_tasks: window did not advance (i=%s, next=%s)",
                i_at,
                i_next,
            )
            return None
        i_at = i_next

    return out
