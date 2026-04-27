# Copyright (c) ModelScope Contributors. All rights reserved.
"""tiktoken counting and Unicode-safe truncation for LLM prompt sizing."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Callable, List

from .jsonl_session_messages import message_body_for_llm, segment_fingerprint_canonical_json

try:
    import tiktoken
except ImportError:
    tiktoken = None


TokenCounter = Callable[[str], int]

# Roles included when joining/splitting conversation text for LLM prompts.
CONVERSATION_ROLES = ("user", "assistant", "tool", "system")


@lru_cache(maxsize=8)
def _tiktoken_counter(encoding_name: str) -> TokenCounter:
    if tiktoken is None:
        raise RuntimeError(
            "tiktoken is required for token counting (pip install tiktoken).",
        )
    enc = tiktoken.get_encoding(encoding_name)

    def count(text: str) -> int:
        if not text:
            return 0
        return len(enc.encode(text))

    return count


def get_token_counter(tiktoken_encoding: str = "cl100k_base") -> TokenCounter:
    """Build count(text)->int for a tiktoken encoding name (see LLMService config)."""
    return _tiktoken_counter(tiktoken_encoding)


# Characters treated as sentence boundaries for graceful truncation.
_SENTENCE_BOUNDARIES = frozenset("。！？；\n.!?;")


def _snap_to_sentence_boundary(text: str, pos: int) -> int:
    """Return the largest index <= *pos* that sits right after a sentence boundary.

    Scans backwards from *pos*.  If no boundary is found within 20% of *pos*,
    returns *pos* unchanged to avoid over-shortening.
    """
    if pos <= 0:
        return pos
    floor = max(0, int(pos * 0.8))
    for i in range(pos, floor, -1):
        if text[i - 1] in _SENTENCE_BOUNDARIES:
            return i
    return pos


def truncate_text_to_token_limit(
    text: str,
    max_tokens: int,
    count_tokens: TokenCounter,
) -> str:
    """Truncate text so count_tokens stays <= max_tokens.

    Uses binary search on prefix length, then snaps back to the nearest
    sentence boundary (。！？；.!?; or newline) to avoid mid-sentence cuts.
    Appends '…' when the text is actually truncated.
    """
    if max_tokens <= 0 or not text:
        return ""
    if count_tokens(text) <= max_tokens:
        return text

    # Reserve token budget for the ellipsis marker
    ellipsis = "…"
    ellipsis_cost = count_tokens(ellipsis)
    effective_max = max(1, max_tokens - ellipsis_cost)

    lo, hi = 0, len(text)
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        chunk = text[:mid]
        n = count_tokens(chunk)
        if n <= effective_max:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1

    best = _snap_to_sentence_boundary(text, best)
    result = text[:best].rstrip()
    if result and len(result) < len(text):
        result += ellipsis
    return result


def join_messages_lines_within_token_budget(
    messages: List[dict],
    max_tokens: int,
    count_tokens: TokenCounter,
    *,
    roles: tuple = CONVERSATION_ROLES,
) -> str:
    """Append [role]: content lines in order; truncate the last body if needed to fit."""
    if max_tokens <= 0:
        return ""

    lines: List[str] = []
    used = 0

    for msg in messages:
        role = msg.get("role", "")
        if role not in roles:
            continue
        body = message_body_for_llm(msg)
        if not body:
            continue
        line = f"[{role}]: {body}"
        line_tokens = count_tokens(line)
        if line_tokens <= max_tokens - used:
            lines.append(line)
            used += line_tokens
            continue
        remaining = max_tokens - used
        if remaining <= 0:
            break
        prefix = f"[{role}]: "
        p_tokens = count_tokens(prefix)
        if p_tokens >= remaining:
            break
        body_budget = remaining - p_tokens
        body = truncate_text_to_token_limit(body, body_budget, count_tokens)
        if body:
            lines.append(prefix + body)
        break

    return "\n".join(lines)


def join_messages_full_text(
    messages: List[dict],
    roles: tuple = CONVERSATION_ROLES,
) -> str:
    """Join messages as [role]: lines without truncation."""
    lines: List[str] = []
    for msg in messages:
        role = msg.get("role", "")
        if role not in roles:
            continue
        body = message_body_for_llm(msg)
        if not body:
            continue
        lines.append(f"[{role}]: {body}")
    return "\n".join(lines)


def split_messages_into_token_windows(
    messages: List[dict],
    window_tokens: int,
    count_tokens: TokenCounter,
    *,
    roles: tuple = CONVERSATION_ROLES,
) -> List[List[dict]]:
    """Split user/assistant messages into consecutive chunks under window_tokens each."""
    wt = max(256, int(window_tokens)) if window_tokens and window_tokens > 0 else 65536

    normalized: List[dict] = []
    for msg in messages:
        role = msg.get("role", "")
        if role not in roles:
            continue
        if not message_body_for_llm(msg):
            continue
        normalized.append(dict(msg))

    if not normalized:
        return []

    def blob_toks(ms: List[dict]) -> int:
        b = join_messages_full_text(ms, roles)
        return count_tokens(b) if b else 0

    def truncate_one(msg: dict) -> dict:
        role = msg.get("role", "")
        body = message_body_for_llm(msg)
        prefix = f"[{role}]: "
        p_tok = count_tokens(prefix)
        if p_tok >= wt:
            return {"role": role, "content": " "}
        body_budget = max(1, wt - p_tok)
        body = truncate_text_to_token_limit(body, body_budget, count_tokens)
        if not body.strip():
            body = " "
        # Lossy: oversized native messages become plain {role, content} in this chunk.
        return {"role": role, "content": body}

    chunks: List[List[dict]] = []
    current: List[dict] = []

    for msg in normalized:
        if blob_toks([msg]) > wt:
            if current:
                chunks.append(current)
                current = []
            chunks.append([truncate_one(msg)])
            continue

        if not current:
            current = [msg]
            continue

        test = current + [msg]
        if blob_toks(test) <= wt:
            current = test
        else:
            chunks.append(current)
            current = [msg]

    if current:
        chunks.append(current)
    return chunks


def compute_segment_fingerprint(messages: List[dict]) -> str:
    """SHA-256 fingerprint from canonical native message JSON. 16-char hex."""
    raw = segment_fingerprint_canonical_json(messages)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
