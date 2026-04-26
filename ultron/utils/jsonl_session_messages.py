# Copyright (c) ModelScope Contributors. All rights reserved.
"""Parse agent session JSONL for trajectory segmentation and extraction.

Two session shapes are supported:

- **openai**: string ``content``, optional ``tool_calls`` / ``reasoning_content``,
  separate ``role: tool`` rows.
- **anthropic**: OpenClaw / Messages API style ``content`` as blocks
  (``text``, ``thinking``, ``tool_use``, ``tool_result``).

Use ``session_format="auto"`` (default) to scan the file once and pick a template,
or force ``"openai"`` / ``"anthropic"``. Normalized output is the same native
dict list in both modes.
"""
from __future__ import annotations

import json
from typing import Any, List, Literal, Optional

JsonlSessionFormat = Literal["openai", "anthropic", "auto"]

_AGENT_ROLES = frozenset({"user", "assistant", "tool", "system"})
# Blocks seen in Anthropic Messages API and OpenClaw exports.
_ANTHROPIC_BLOCK_TYPES = frozenset({"text", "thinking", "tool_use", "tool_result"})


def _looks_like_anthropic_blocks(content: Any) -> bool:
    """True if *content* is a list of Anthropic-style blocks."""
    if not isinstance(content, list) or not content:
        return False
    has_non_text = False
    for b in content:
        if not isinstance(b, dict):
            return False
        t = b.get("type")
        if t not in _ANTHROPIC_BLOCK_TYPES:
            return False
        if t != "text":
            has_non_text = True
        elif "text" not in b:
            return False
    return has_non_text or all(
        isinstance(b, dict) and b.get("type") == "text" for b in content
    )


def detect_jsonl_session_format(
    lines: List[str],
    *,
    max_lines_to_scan: int = 500,
) -> Literal["openai", "anthropic"]:
    """Scan initial JSONL rows; if any message uses Anthropic blocks, return ``anthropic``."""
    scanned = 0
    for raw in lines:
        if scanned >= max_lines_to_scan:
            break
        raw = raw.strip()
        if not raw:
            continue
        scanned += 1
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if obj.get("_type") == "metadata":
            continue
        if obj.get("role", "") not in _AGENT_ROLES:
            continue
        if _looks_like_anthropic_blocks(obj.get("content")):
            return "anthropic"
    return "openai"


def _tool_result_body(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(content)


def _anthropic_tool_use_to_openai(block: dict[str, Any]) -> dict[str, Any]:
    tid = block.get("id") or ""
    name = block.get("name") or ""
    inp = block.get("input")
    if isinstance(inp, str):
        args = inp
    else:
        try:
            args = json.dumps(inp if inp is not None else {}, ensure_ascii=False)
        except (TypeError, ValueError):
            args = str(inp)
    return {
        "id": tid,
        "type": "function",
        "function": {"name": name, "arguments": args},
    }


def _native_from_anthropic_user_blocks(blocks: List[dict[str, Any]]) -> List[dict[str, Any]]:
    """One JSONL user row with content blocks -> user + tool native rows (order preserved)."""
    out: List[dict[str, Any]] = []
    text_buf: List[str] = []
    for block in blocks:
        t = block.get("type")
        if t == "text":
            text_buf.append(block.get("text") or "")
        elif t == "tool_result":
            if text_buf:
                merged = "\n".join(text_buf).strip()
                if merged:
                    out.append({"role": "user", "content": merged})
                text_buf = []
            out.append(
                {
                    "role": "tool",
                    "content": _tool_result_body(block.get("content")),
                    "name": "",
                    "tool_call_id": (block.get("tool_use_id") or "") or "",
                }
            )
        else:
            continue
    if text_buf:
        merged = "\n".join(text_buf).strip()
        if merged:
            out.append({"role": "user", "content": merged})
    return out


def _assistant_turn_metadata(source: dict[str, Any]) -> dict[str, Any]:
    """Fields preserved on native assistant rows but omitted from LLM formatting."""
    sr = source.get("stop_reason")
    if sr is None:
        return {}
    s = str(sr).strip()
    if not s:
        return {}
    return {"stop_reason": s}


def _native_from_anthropic_assistant_blocks(
    blocks: List[dict[str, Any]],
) -> dict[str, Any]:
    reasoning_parts: List[str] = []
    text_parts: List[str] = []
    tool_calls: List[dict[str, Any]] = []
    for block in blocks:
        t = block.get("type")
        if t == "thinking":
            s = (block.get("thinking") or "").strip()
            if s:
                reasoning_parts.append(s)
        elif t == "text":
            text_parts.append(block.get("text") or "")
        elif t == "tool_use":
            tool_calls.append(_anthropic_tool_use_to_openai(block))
    return {
        "role": "assistant",
        "content": "\n".join(text_parts).strip(),
        "tool_calls": tool_calls if tool_calls else None,
        "reasoning_content": "\n\n".join(reasoning_parts).strip(),
    }


def _native_from_anthropic_system_blocks(blocks: List[dict[str, Any]]) -> dict[str, Any]:
    parts: List[str] = []
    for block in blocks:
        if block.get("type") == "text":
            parts.append(block.get("text") or "")
        elif block.get("type") == "thinking":
            parts.append(block.get("thinking") or "")
    return {"role": "system", "content": "\n".join(parts).strip()}


def _coerce_list_content_to_string(content: Any) -> str:
    try:
        return json.dumps(content, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(content)


def _append_openai_style_message(out: List[dict[str, Any]], obj: dict[str, Any], role: str) -> None:
    if role == "user":
        c = obj.get("content", "")
        out.append(
            {
                "role": "user",
                "content": c if isinstance(c, str) else str(c),
            }
        )
    elif role == "system":
        c = obj.get("content", "")
        out.append(
            {
                "role": "system",
                "content": c if isinstance(c, str) else str(c),
            }
        )
    elif role == "tool":
        out.append(
            {
                "role": "tool",
                "content": obj.get("content", ""),
                "name": obj.get("name", "") or "",
                "tool_call_id": obj.get("tool_call_id", "") or "",
            }
        )
    else:
        row: dict[str, Any] = {
            "role": "assistant",
            "content": obj.get("content", "") or "",
            "tool_calls": obj.get("tool_calls"),
            "reasoning_content": obj.get("reasoning_content", "") or "",
        }
        row.update(_assistant_turn_metadata(obj))
        out.append(row)


def _parse_agent_jsonl_lines_openai(lines: List[str]) -> List[dict[str, Any]]:
    """Template: OpenAI / nanobot string content and explicit tool rows."""
    out: List[dict[str, Any]] = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if obj.get("_type") == "metadata":
            continue
        role = obj.get("role", "")
        if role not in _AGENT_ROLES:
            continue

        content = obj.get("content")
        if isinstance(content, list):
            if role == "user":
                out.append({"role": "user", "content": _coerce_list_content_to_string(content)})
            elif role == "assistant":
                row = {
                    "role": "assistant",
                    "content": _coerce_list_content_to_string(content),
                    "tool_calls": obj.get("tool_calls"),
                    "reasoning_content": obj.get("reasoning_content", "") or "",
                }
                row.update(_assistant_turn_metadata(obj))
                out.append(row)
            elif role == "system":
                out.append({"role": "system", "content": _coerce_list_content_to_string(content)})
            else:
                _append_openai_style_message(out, obj, role)
            continue

        _append_openai_style_message(out, obj, role)
    return out


def _parse_agent_jsonl_lines_anthropic(lines: List[str]) -> List[dict[str, Any]]:
    """Template: Anthropic / OpenClaw content block arrays."""
    out: List[dict[str, Any]] = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if obj.get("_type") == "metadata":
            continue
        role = obj.get("role", "")
        if role not in _AGENT_ROLES:
            continue

        content = obj.get("content")
        if role == "user":
            if isinstance(content, list) and _looks_like_anthropic_blocks(content):
                out.extend(_native_from_anthropic_user_blocks(content))
            elif isinstance(content, list):
                out.append({"role": "user", "content": _coerce_list_content_to_string(content)})
            else:
                _append_openai_style_message(out, obj, role)
            continue

        if role == "assistant":
            if isinstance(content, list) and _looks_like_anthropic_blocks(content):
                row = _native_from_anthropic_assistant_blocks(content)
                row.update(_assistant_turn_metadata(obj))
                out.append(row)
            elif isinstance(content, list):
                row = {
                    "role": "assistant",
                    "content": _coerce_list_content_to_string(content),
                    "tool_calls": obj.get("tool_calls"),
                    "reasoning_content": obj.get("reasoning_content", "") or "",
                }
                row.update(_assistant_turn_metadata(obj))
                out.append(row)
            else:
                _append_openai_style_message(out, obj, role)
            continue

        if role == "system":
            if isinstance(content, list) and _looks_like_anthropic_blocks(content):
                out.append(_native_from_anthropic_system_blocks(content))
            elif isinstance(content, list):
                out.append({"role": "system", "content": _coerce_list_content_to_string(content)})
            else:
                _append_openai_style_message(out, obj, role)
            continue

        if role == "tool":
            _append_openai_style_message(out, obj, role)
            continue

        _append_openai_style_message(out, obj, role)
    return out


def parse_agent_jsonl_lines(
    lines: List[str],
    *,
    session_format: JsonlSessionFormat = "auto",
) -> List[dict[str, Any]]:
    """Parse JSONL lines to native messages using the chosen session template."""
    fmt = session_format
    if fmt == "auto":
        fmt = detect_jsonl_session_format(lines)
    elif fmt not in ("openai", "anthropic"):
        raise ValueError(
            f"session_format must be 'auto', 'openai', or 'anthropic', got {session_format!r}",
        )

    if fmt == "anthropic":
        return _parse_agent_jsonl_lines_anthropic(lines)
    return _parse_agent_jsonl_lines_openai(lines)


def _expand_one_message(msg: dict[str, Any]) -> Optional[dict[str, str]]:
    """Render one message as {role, content} for LLM line text only (not for storage).

    Ignores ``stop_reason`` and other turn metadata.
    """
    role = msg.get("role", "")
    if role == "user":
        c = (msg.get("content") or "").strip()
        if not c:
            return None
        return {"role": "user", "content": c}
    if role == "system":
        c = (msg.get("content") or "").strip()
        if not c:
            return None
        return {"role": "system", "content": c}
    if role == "tool":
        c = msg.get("content", "")
        name = (msg.get("name") or "").strip()
        tid = (msg.get("tool_call_id") or "").strip()
        header_parts = []
        if name:
            header_parts.append(f"name={name}")
        if tid:
            header_parts.append(f"id={tid}")
        header = f"({', '.join(header_parts)})" if header_parts else ""
        body = c.strip() if isinstance(c, str) else str(c).strip()
        if not body and not header:
            # Keep the row in the trajectory; segmentation uses empty body line
            return {"role": "tool", "content": ""}
        text = f"{header}\n{body}" if header and body else (header or body)
        return {"role": "tool", "content": text}
    if role == "assistant":
        parts: List[str] = []
        r = (msg.get("reasoning_content") or "").strip()
        if r:
            parts.append(f"[reasoning]\n{r}")
        tc = msg.get("tool_calls")
        if tc:
            try:
                parts.append("[tool_calls]\n" + json.dumps(tc, ensure_ascii=False))
            except (TypeError, ValueError):
                parts.append("[tool_calls]\n" + str(tc))
        c = (msg.get("content") or "").strip()
        if c:
            parts.append(c)
        if not parts:
            return None
        return {"role": "assistant", "content": "\n\n".join(parts)}
    return None


def message_body_for_llm(msg: dict[str, Any]) -> str:
    """Plain-text body for prompts and token counting (derived from native fields)."""
    plain = _expand_one_message(msg)
    return plain["content"] if plain else ""


def filter_messages_for_trajectory(messages: List[dict[str, Any]]) -> List[dict[str, Any]]:
    """Drop lines with nothing to show after native-field rules."""
    return [m for m in messages if _expand_one_message(m) is not None]


def parse_jsonl_lines_for_trajectory(
    lines: List[str],
    *,
    session_format: JsonlSessionFormat = "auto",
) -> List[dict[str, Any]]:
    """JSONL lines -> native message dicts for TrajectoryService (filtered).

    Assistant rows may include ``stop_reason`` from the source JSON when present;
    it is not part of :func:`message_body_for_llm` output.
    """
    return filter_messages_for_trajectory(
        parse_agent_jsonl_lines(lines, session_format=session_format),
    )


def expand_parsed_messages_to_plain(
    messages: List[dict[str, Any]],
) -> List[dict[str, str]]:
    """Optional: collapse to {role, content} for legacy callers."""
    plain: List[dict[str, str]] = []
    for msg in messages:
        one = _expand_one_message(msg)
        if one:
            plain.append(one)
    return plain


def canonical_message_dict(msg: dict[str, Any]) -> dict[str, Any]:
    """Stable dict for fingerprinting (normalized native shape)."""
    role = msg.get("role") or ""
    if role == "user":
        return {"role": "user", "content": (msg.get("content") or "").strip()}
    if role == "system":
        return {"role": "system", "content": (msg.get("content") or "").strip()}
    if role == "tool":
        c = msg.get("content", "")
        body = c if isinstance(c, str) else str(c)
        return {
            "role": "tool",
            "content": body,
            "name": (msg.get("name") or "").strip(),
            "tool_call_id": (msg.get("tool_call_id") or "").strip(),
        }
    if role == "assistant":
        d: dict[str, Any] = {
            "role": "assistant",
            "content": (msg.get("content") or "").strip(),
            "reasoning_content": (msg.get("reasoning_content") or "").strip(),
            "tool_calls": msg.get("tool_calls"),
        }
        sr = msg.get("stop_reason")
        if sr is not None and str(sr).strip():
            d["stop_reason"] = str(sr).strip()
        return d
    return {"role": role}


def segment_fingerprint_canonical_json(messages: List[dict[str, Any]]) -> str:
    """Single JSON blob for hashing a message list (order preserved)."""
    payload = [canonical_message_dict(m) for m in messages]
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
