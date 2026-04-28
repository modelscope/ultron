# Copyright (c) ModelScope Contributors. All rights reserved.
import json
import logging
import os
from typing import List, Optional

from ..core.llm_service import LLMService
from .token_budget import truncate_text_to_token_limit

logger = logging.getLogger(__name__)


_MEMORY_EXTRACTION_PROMPT = """Analyze the following text and extract all reusable experiences or knowledge as structured memories.

Rules:
- Extract each distinct experience as a separate memory entry
- Only extract genuinely reusable knowledge; skip one-off or context-specific details
- If a field has no meaningful value, use an empty string — do not omit the key
- tags should be concise keywords (2–5 per entry)

Return strictly as a JSON array with no other text:
```json
[
  {
    "content": "Core experience (describe the problem and key insight in detail)",
    "context": "When and where this occurs (environment, trigger conditions)",
    "resolution": "Solution or recommendation (empty string if not applicable)",
    "tags": ["tag1", "tag2"]
  }
]
```

Text to analyze:
"""

_MEMORY_TYPE_CLASSIFY_ALLOWED = frozenset(
    {
        "error",
        "security",
        "correction",
        "pattern",
        "preference",
        "life",
    }
)

_CLASSIFY_MEMORY_TYPE_PROMPT = """You are a memory classifier. Given the fields below, choose exactly one type for this shared memory.

Types (lowercase only):
- error: technical failures, stack traces, exceptions, environment/dependency issues
- security: security incidents, vulnerabilities, breaches, hardening, compliance
- correction: fixing wrong assumptions, wrong operations, or common misconceptions
- pattern: reusable practices, workflows, conventions, best practices (not a single incident)
- preference: shareable team conventions or collaboration norms (not personal profiles)
- life: objective, generalizable life tips (exclude personal medical advice or sensitive privacy)

Return only JSON, no other text. Example: {"memory_type": "error"}

Memory to classify:

"""


class LLMOrchestrator:
    """LLM-driven business operations: memory extraction, merging, classification, skill evolution."""

    def __init__(
        self,
        llm_service: LLMService,
        classify_llm_service: Optional[LLMService] = None,
        quality_llm_service: Optional[LLMService] = None,
    ):
        self.llm = llm_service
        self.classify_llm = classify_llm_service or llm_service
        self.quality_llm = quality_llm_service

    def prepare_conversation_text_for_memory_extraction(
        self,
        messages: List[dict],
        *,
        max_conversation_tokens: Optional[int] = None,
    ) -> str:
        """
        Join conversation messages into a single string within a token budget.

        If max_conversation_tokens is given (e.g. a sliding-window chunk limit),
        that value is used directly; otherwise the budget is derived from the
        extraction prompt overhead.
        """
        from .token_budget import join_messages_lines_within_token_budget

        if max_conversation_tokens is not None:
            max_toks = max(256, int(max_conversation_tokens))
        else:
            max_toks = self.llm.user_text_token_budget(_MEMORY_EXTRACTION_PROMPT)
        return join_messages_lines_within_token_budget(
            messages, max_toks, self.llm._count_tokens
        )

    def segment_conversation_tasks(
        self, messages: List[dict]
    ) -> Optional[List[dict]]:
        """Split a conversation into distinct task segments using LLM windows."""
        from ..services.trajectory.segmentation_llm import (
            segment_conversation_tasks_with_llm,
        )

        return segment_conversation_tasks_with_llm(self.llm, messages)

    def extract_memories_from_text(self, text: str) -> List[dict]:
        """
        Extract structured memories from raw text.

        Returns a list of dicts with keys: content, context, resolution, tags.
        Returns [] on LLM failure or unparseable response.
        """
        max_toks = self.llm.user_text_token_budget(_MEMORY_EXTRACTION_PROMPT)
        truncated = truncate_text_to_token_limit(text, max_toks, self.llm._count_tokens)
        response = self.llm.call(
            self.llm.dashscope_user_messages(_MEMORY_EXTRACTION_PROMPT + truncated)
        )
        if not response:
            return []
        result = self.llm.parse_json_response(response)
        return result if isinstance(result, list) else []

    def summarize_for_l0_l1(
        self,
        content: str,
        context: str,
        resolution: str,
        *,
        l0_max_tokens: Optional[int] = None,
        l1_max_tokens: Optional[int] = None,
    ) -> Optional[dict]:
        """
        Generate L0 (one-line summary) and L1 (key overview) for a memory record.

        Returns {"summary_l0": "...", "overview_l1": "..."} or None on failure.
        """
        l0m = int(l0_max_tokens or os.environ.get("ULTRON_L0_MAX_TOKENS", "64"))
        l1m = int(l1_max_tokens or os.environ.get("ULTRON_L1_MAX_TOKENS", "256"))

        prompt_prefix = (
            f"Generate two levels of summary for the following memory record.\n\n"
            f"L0: one sentence (≤{l0m} tokens) capturing the core takeaway.\n"
            f"L1: a brief overview (≤{l1m} tokens) covering the problem, scenario, and solution.\n\n"
            f"Return strictly in JSON:\n"
            f"```json\n"
            f'{{"summary_l0": "one-line summary", "overview_l1": "brief overview"}}\n'
            f"```\n\n"
            f"Memory:\n"
        )
        combined = f"Content: {content}\nContext: {context}\nResolution: {resolution}"
        max_toks = self.llm.user_text_token_budget(prompt_prefix)
        truncated = truncate_text_to_token_limit(
            combined, max_toks, self.llm._count_tokens
        )

        response = self.llm.call(
            self.llm.dashscope_user_messages(prompt_prefix + truncated)
        )
        if not response:
            return None

        result = self.llm.parse_json_response(response, expect_array=False)
        if not isinstance(result, dict):
            return None

        s0 = result.get("summary_l0", "") or ""
        s1 = result.get("overview_l1", "") or ""
        if l0m > 0:
            s0 = truncate_text_to_token_limit(s0, l0m, self.llm._count_tokens)
        if l1m > 0:
            s1 = truncate_text_to_token_limit(s1, l1m, self.llm._count_tokens)
        return {"summary_l0": s0, "overview_l1": s1}

    def confirm_memory_duplicate(
        self,
        existing_content: str,
        existing_context: str,
        new_content: str,
        new_context: str,
    ) -> bool:
        """Ask the LLM whether two memories describe the same topic and should be merged.

        Used as a second-stage check when embedding similarity falls in the
        soft-threshold range (e.g. 0.75–0.85).  Returns ``True`` to merge.
        """
        _trunc = lambda t: truncate_text_to_token_limit(
            t, 512, self.classify_llm._count_tokens
        )
        prompt = (
            "You are a memory deduplication judge. Decide whether the two memories "
            "below describe essentially the same topic / experience and should be "
            "merged into one.\n\n"
            "Rules:\n"
            "- If they cover the same core subject (even with different wording or "
            "detail level), answer YES.\n"
            "- If they cover clearly different subjects that merely share a keyword, "
            "answer NO.\n\n"
            f"Memory A:\n- Content: {_trunc(existing_content)}\n"
            f"- Context: {_trunc(existing_context)}\n\n"
            f"Memory B:\n- Content: {_trunc(new_content)}\n"
            f"- Context: {_trunc(new_context)}\n\n"
            'Return only JSON: {"should_merge": true} or {"should_merge": false}'
        )
        response = self.classify_llm.call(
            self.classify_llm.dashscope_user_messages(prompt)
        )
        if not response:
            return False
        try:
            obj = json.loads(response.strip().strip("`").strip())
            return bool(obj.get("should_merge", False))
        except (json.JSONDecodeError, AttributeError):
            lower = response.strip().lower()
            return '"should_merge": true' in lower or '"should_merge":true' in lower

    def merge_memories(
        self,
        old_content: str,
        old_context: str,
        old_resolution: str,
        new_content: str,
        new_context: str,
        new_resolution: str,
        *,
        max_field_tokens: int = 0,
    ) -> Optional[dict]:
        """
        Merge two similar memories into one abstracted, generalized memory.

        Returns {"content": "...", "context": "...", "resolution": "..."} or None.
        """
        cap_instruction = ""
        if max_field_tokens > 0:
            cap_instruction = (
                f"\n5. Keep each output field within {max_field_tokens} tokens; "
                "drop lower-value detail if needed to fit.\n"
            )

        _fixed = (
            "You are a memory consolidation expert. Merge the two memories below "
            "into one more general, abstracted memory.\n\nRequirements:\n1. ...\n"
            "Return strictly in JSON:\n```json\n{...}\n```\n\n"
            "Existing memory:\n- Content: \n- Context: \n- Resolution: \n\n"
            "New memory:\n- Content: \n- Context: \n- Resolution: "
        ) + cap_instruction
        per_field = max(self.llm.user_text_token_budget(_fixed) // 6, 64)

        old_content = truncate_text_to_token_limit(
            old_content, per_field, self.llm._count_tokens
        )
        old_context = truncate_text_to_token_limit(
            old_context, per_field, self.llm._count_tokens
        )
        old_resolution = truncate_text_to_token_limit(
            old_resolution, per_field, self.llm._count_tokens
        )
        new_content = truncate_text_to_token_limit(
            new_content, per_field, self.llm._count_tokens
        )
        new_context = truncate_text_to_token_limit(
            new_context, per_field, self.llm._count_tokens
        )
        new_resolution = truncate_text_to_token_limit(
            new_resolution, per_field, self.llm._count_tokens
        )

        prompt = f"""You are a memory consolidation expert. Merge the two memories below into one more general, abstracted memory.

Requirements:
1. Extract the common pattern; remove overly specific details; keep the general rule.
2. If both describe different instances of the same class of problem, produce one memory covering that class.
3. Synthesize — do NOT simply concatenate.
4. Preserve key technical details and actionable solutions.{cap_instruction}
Return strictly in JSON:
```json
{{
  "content": "merged memory content",
  "context": "merged context/scenario",
  "resolution": "merged solution"
}}
```

Existing memory:
- Content: {old_content}
- Context: {old_context}
- Resolution: {old_resolution}

New memory:
- Content: {new_content}
- Context: {new_context}
- Resolution: {new_resolution}"""

        response = self.llm.call(self.llm.dashscope_user_messages(prompt))
        if not response:
            return None
        result = self.llm.parse_json_response(response, expect_array=False)
        if not isinstance(result, dict) or not result.get("content"):
            return None
        c = result.get("content", "") or ""
        ctx = result.get("context", "") or ""
        res = result.get("resolution", "") or ""
        if max_field_tokens > 0:
            c = truncate_text_to_token_limit(
                c, max_field_tokens, self.llm._count_tokens
            )
            ctx = truncate_text_to_token_limit(
                ctx, max_field_tokens, self.llm._count_tokens
            )
            res = truncate_text_to_token_limit(
                res, max_field_tokens, self.llm._count_tokens
            )
        return {"content": c, "context": ctx, "resolution": res}

    def classify_memory_type(
        self,
        content: str,
        context: str = "",
        resolution: str = "",
        *,
        max_body_tokens: int = 3072,
    ) -> Optional[str]:
        """
        Classify a memory into one of the allowed types using LLM.

        Returns one of: error, security, correction, pattern, preference, life.
        Returns None if unavailable, call fails, or output is not a valid type.
        """
        if not self.classify_llm.is_available:
            return None
        combined = (
            f"content:\n{content or '(empty)'}\n\n"
            f"context:\n{context or '(empty)'}\n\n"
            f"resolution:\n{resolution or '(empty)'}"
        )
        truncated = truncate_text_to_token_limit(
            combined, max_body_tokens, self.classify_llm._count_tokens
        )
        response = self.classify_llm.call(
            self.classify_llm.dashscope_user_messages(
                _CLASSIFY_MEMORY_TYPE_PROMPT + truncated
            )
        )
        if not response:
            return None
        result = self.classify_llm.parse_json_response(response, expect_array=False)
        if not isinstance(result, dict):
            return None
        mt = (result.get("memory_type") or "").strip().lower()
        return mt if mt in _MEMORY_TYPE_CLASSIFY_ALLOWED else None

    # ============ Skill Evolution (Cluster Crystallization) ============
    #
    # Reference: SkillClaw (https://github.com/AMAP-ML/SkillClaw).
    # Prompts below borrow high-level ideas: crystallization / evolve constraints (environment-specific vs generic guidance, source-of-truth edits, targeted changes over full rewrites) and publication-style verification.
    # ============

    def crystallize_skill_from_cluster(
        self,
        memories: List[dict],
        topic: str = "",
    ) -> Optional[dict]:
        """Synthesize a multi-step workflow skill from a cluster of related memories.

        Returns {"name": "...", "description": "...", "content": "..."} or None.
        Returns {"quality": "insufficient"} if memories are too scattered.
        """
        # Prompt constraints borrowed from SkillClaw.
        memories_text = self._format_memories_for_prompt(memories)
        prompt = f"""You are a knowledge engineer. Below are {len(memories)} experience records from the same domain{f' ({topic})' if topic else ''}.
Synthesize them into an executable multi-step workflow skill.

Requirements:
1. Extract common patterns and a complete workflow — do NOT simply list each experience
2. Must include:
   - Trigger conditions (when to use this skill)
   - Step sequence (≥3 steps, each with clear input/output)
   - Edge case handling (common exceptions and fallbacks)
   - Decision branches (if different situations need different handling)
3. If multiple solutions exist, rank by reliability
4. Write as instructions an agent can follow immediately
5. Compress environment-specific information (API endpoints, ports, commands, payload formats) — not generic best practices

If these experiences are too scattered to form a coherent workflow, return {{"quality": "insufficient"}}.

Experience records:
{memories_text}

Return strictly as JSON:
```json
{{
  "name": "short-kebab-case-name",
  "description": "One sentence: what this skill does and when to use it",
  "content": "Full markdown skill document with ## sections"
}}
```"""
        response = self.llm.call(self.llm.dashscope_user_messages(prompt))
        if not response:
            return None
        result = self.llm.parse_json_response(response, expect_array=False)
        if not isinstance(result, dict):
            return None
        if result.get("quality") == "insufficient":
            return result
        if not result.get("content"):
            return None
        return {
            "name": result.get("name", ""),
            "description": result.get("description", ""),
            "content": result.get("content", ""),
        }

    def recrystallize_skill(
        self,
        current_skill_content: str,
        current_version: str,
        memories: List[dict],
        new_memory_count: int,
    ) -> Optional[dict]:
        """Re-crystallize an existing skill with new knowledge from its cluster.

        Returns {"name", "description", "content"} or {"evolution": "unnecessary"} or None.
        """
        memories_text = self._format_memories_for_prompt(memories)
        # Editing principles borrowed from SkillClaw.
        prompt = f"""You are a knowledge engineer. Below is an existing skill and all experience records from its domain.
Enhance the skill with new knowledge.

Current skill (v{current_version}):
{truncate_text_to_token_limit(current_skill_content, 4000, self.llm._count_tokens)}

All domain experiences ({len(memories)} total, {new_memory_count} are new):
{memories_text}

Requirements:
1. Treat the current skill as source of truth — default to targeted edits, not rewrites
2. Incorporate new knowledge: add new steps, edge cases, alternative approaches
3. If new experiences contradict existing content, prefer the more reliable one
4. Do NOT lower overall quality just to incorporate new content
5. Preserve concrete environment information (API endpoints, ports, commands) unless evidence shows they changed

If new experiences add no substantial value, return {{"evolution": "unnecessary"}}.

Return strictly as JSON:
```json
{{
  "name": "keep-or-improve-name",
  "description": "keep or improve description",
  "content": "Full updated markdown skill document"
}}
```"""
        response = self.llm.call(self.llm.dashscope_user_messages(prompt))
        if not response:
            return None
        result = self.llm.parse_json_response(response, expect_array=False)
        if not isinstance(result, dict):
            return None
        if result.get("evolution") == "unnecessary":
            return result
        if not result.get("content"):
            return None
        return {
            "name": result.get("name", ""),
            "description": result.get("description", ""),
            "content": result.get("content", ""),
        }

    def verify_skill(
        self,
        skill_content: str,
        memories: List[dict],
        is_recrystallization: bool = False,
    ) -> Optional[dict]:
        """Independent LLM verification: structure scoring + faithfulness check.

        Returns verification scores or None on failure.
        """
        memories_text = self._format_memories_for_prompt(memories)
        preserve_note = (
            "\n- preserves_existing_value: Did the evolution preserve effective content from the previous version? (0-1)"
            if is_recrystallization else ""
        )
        # Verifier prompt borrowed from SkillClaw.
        prompt = f"""You are an independent skill auditor. Below is a skill synthesized from experience records, along with its source experiences.
Complete two evaluations:

## 1. Faithfulness Check
For each step/claim in the skill:
- Can it be traced to a source experience? → grounded
- No evidence in sources (fabricated)? → hallucinated
- Contradicts source experiences? → contradicted

## 2. Structure Scoring (0-1 each)
- workflow_clarity: Are steps clear, ordered, and executable?
- specificity_and_reusability: Are instructions specific and reusable, not generic advice?{preserve_note}

Skill:
{truncate_text_to_token_limit(skill_content, 4000, self.llm._count_tokens)}

Source experiences ({len(memories)} records):
{memories_text}

Return strictly as JSON:
```json
{{
  "claims": [
    {{"claim": "step summary", "status": "grounded|hallucinated|contradicted", "source_memory_id": "...or null"}}
  ],
  "grounded_in_evidence": 0.85,
  "has_contradiction": false,
  "workflow_clarity": 0.8,
  "specificity_and_reusability": 0.75{', "preserves_existing_value": 0.8' if is_recrystallization else ''}
}}
```"""
        response = self.llm.call(self.llm.dashscope_user_messages(prompt))
        if not response:
            return None
        result = self.llm.parse_json_response(response, expect_array=False)
        if not isinstance(result, dict):
            return None
        return result

    def generate_cluster_topic(self, memories: List[dict]) -> str:
        """Generate a short topic label for a cluster of related memories."""
        summaries = []
        for m in memories[:10]:
            l0 = m.get("summary_l0", "") or m.get("content", "")[:100]
            if l0:
                summaries.append(f"- {l0}")
        if not summaries:
            return ""
        prompt = f"""Given these related experience summaries, generate a short topic label (3-8 words, in the language of the content):

{chr(10).join(summaries)}

Return only the topic label, nothing else."""
        response = self.llm.call(self.llm.dashscope_user_messages(prompt))
        return (response or "").strip().strip('"').strip("'")[:80]

    def _format_memories_for_prompt(self, memories: List[dict], max_per_memory: int = 600) -> str:
        """Format a list of memory dicts for LLM prompts."""
        parts = []
        for i, m in enumerate(memories, 1):
            content = truncate_text_to_token_limit(
                m.get("content", ""), max_per_memory // 3, self.llm._count_tokens
            )
            context = truncate_text_to_token_limit(
                m.get("context", ""), max_per_memory // 4, self.llm._count_tokens
            )
            resolution = truncate_text_to_token_limit(
                m.get("resolution", ""), max_per_memory // 3, self.llm._count_tokens
            )
            entry = f"### Experience {i}"
            if m.get("id"):
                entry += f" (id: {m['id'][:8]})"
            entry += f"\n- Content: {content}"
            if context:
                entry += f"\n- Context: {context}"
            if resolution:
                entry += f"\n- Resolution: {resolution}"
            parts.append(entry)
        return "\n\n".join(parts)
