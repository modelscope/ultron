# Copyright (c) ModelScope Contributors. All rights reserved.
import json
import logging
import os
import sys
import time
from typing import Any, Callable, Optional

try:
    import dashscope
    HAS_DASHSCOPE = True
except ImportError:
    HAS_DASHSCOPE = False

from ..utils.token_budget import get_token_counter

logger = logging.getLogger(__name__)


def _parse_first_json_value(text: str) -> Optional[Any]:
    """
    Parse the first JSON object or array from *text*, ignoring leading noise and
    trailing prose after a well-formed value.

    ``first [`` … ``last ]`` slicing is unsafe when the model appends text that
    contains ``]`` (e.g. ``see [note]``); ``raw_decode`` stops at the end of the
    first complete value.
    """
    dec = json.JSONDecoder(strict=False)
    for i, c in enumerate(text):
        if c not in "{[":
            continue
        try:
            val, _end = dec.raw_decode(text, i)
            return val
        except json.JSONDecodeError:
            continue
    return None


class LLMService:
    """
    LLM adapter wrapping the DashScope MultiModalConversation API.

    Pure infrastructure: connection, call, response parsing, token budgeting.
    Business logic (memory extraction, merging, classification, skill generation)
    lives in ``utils.llm_orchestrator.LLMOrchestrator``.
    """

    def __init__(
        self,
        model: str = "qwen3.5-flash",
        api_url: str = "https://dashscope.aliyuncs.com/api/v1",
        max_input_tokens: int = 200_000,
        prompt_reserve_tokens: int = 8192,
        tiktoken_encoding: str = "cl100k_base",
        count_tokens: Optional[Callable[[str], int]] = None,
        request_timeout_seconds: int = 300,
        max_retries: int = 2,
        retry_base_delay_seconds: float = 1.0,
    ):
        self.model = model
        self.api_url = api_url
        self.max_input_tokens = int(max_input_tokens)
        self.prompt_reserve_tokens = int(prompt_reserve_tokens)
        self.request_timeout_seconds = max(30, int(request_timeout_seconds))
        self.max_retries = max(0, int(max_retries))
        self.retry_base_delay_seconds = max(0.0, float(retry_base_delay_seconds))
        self._count_tokens = count_tokens or get_token_counter(tiktoken_encoding)

        if HAS_DASHSCOPE:
            dashscope.base_http_api_url = api_url

    @staticmethod
    def dashscope_user_messages(prompt: str) -> list:
        return [{"role": "user", "content": [{"text": prompt}]}]

    def user_text_token_budget(self, prompt_prefix: str) -> int:
        """Return the token budget available for user-supplied text."""
        overhead = self._count_tokens(prompt_prefix)
        return max(self.max_input_tokens - self.prompt_reserve_tokens - overhead, 256)

    def _message_text_from_response(self, response) -> Optional[str]:
        if not response:
            return None
        output = getattr(response, "output", None)
        if output is None:
            logger.warning(
                "LLM response has no output (status_code=%r, message=%r)",
                getattr(response, "status_code", None),
                getattr(response, "message", None),
            )
            return None
        choices = (
            output.get("choices") if isinstance(output, dict)
            else getattr(output, "choices", None)
        ) or []
        if not choices:
            return None
        first = choices[0]
        if not isinstance(first, dict):
            return None
        message = first.get("message")
        if not isinstance(message, dict):
            message = {}
        content = message.get("content", [])
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    return item["text"]
        elif isinstance(content, str):
            return content
        return None

    def call(self, messages: list) -> Optional[str]:
        """
        Call the LLM and return the text reply, or None if all attempts fail.

        On empty body or transport errors, makes up to ``max_retries + 1`` HTTP
        attempts (first call plus ``max_retries`` retries) with exponential backoff:
        ``retry_base_delay_seconds * 2**attempt``.
        """
        if not HAS_DASHSCOPE:
            logger.warning("dashscope not installed, LLM service unavailable")
            return None

        key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
        if not key:
            logger.warning("DASHSCOPE_API_KEY not set")
            return None

        attempts = self.max_retries + 1
        last_reason = ""

        for attempt in range(attempts):
            try:
                response = dashscope.MultiModalConversation.call(
                    api_key=key,
                    model=self.model,
                    messages=messages,
                    request_timeout=self.request_timeout_seconds,
                )
                text = self._message_text_from_response(response)
                if text is not None:
                    return text
                last_reason = "empty or unparsed LLM body"
                logger.warning(
                    "LLM call returned no text (attempt %s/%s, status=%r)",
                    attempt + 1,
                    attempts,
                    getattr(response, "status_code", None) if response else None,
                )
            except Exception as e:
                last_reason = str(e)
                logger.warning(
                    "LLM call failed (attempt %s/%s): %s",
                    attempt + 1,
                    attempts,
                    e,
                )

            if attempt < self.max_retries and self.retry_base_delay_seconds > 0:
                delay = self.retry_base_delay_seconds * (2 ** attempt)
                time.sleep(delay)

        logger.warning("LLM call exhausted after %s attempts: %s", attempts, last_reason)
        return None

    def parse_json_response(self, response: str, expect_array: bool = True):
        """Parse a JSON response from the LLM, stripping markdown code fences."""
        text = response.strip()

        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start) if "```" in text[start:] else len(text)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start) if "```" in text[start:] else len(text)
            text = text[start:end].strip()

        _loads_kw = {}
        if sys.version_info >= (3, 9):
            _loads_kw["strict"] = False

        try:
            return json.loads(text, **_loads_kw)
        except json.JSONDecodeError:
            pass

        parsed = _parse_first_json_value(text)
        if parsed is not None:
            return parsed

        for start_char, end_char in [("[", "]"), ("{", "}")]:
            try:
                s = text.index(start_char)
                e = text.rindex(end_char) + 1
                return json.loads(text[s:e], **_loads_kw)
            except (ValueError, json.JSONDecodeError):
                continue
        logger.warning("Failed to parse LLM JSON response: %s...", text[:200])
        return [] if expect_array else {}

    @property
    def is_available(self) -> bool:
        """Return True if dashscope is installed and DASHSCOPE_API_KEY is set."""
        return HAS_DASHSCOPE and bool(os.environ.get("DASHSCOPE_API_KEY", "").strip())

    def get_info(self) -> dict:
        return {
            "model": self.model,
            "api_url": self.api_url,
            "is_available": self.is_available,
            "has_dashscope": HAS_DASHSCOPE,
            "max_input_tokens": self.max_input_tokens,
            "prompt_reserve_tokens": self.prompt_reserve_tokens,
            "request_timeout_seconds": self.request_timeout_seconds,
            "max_retries": self.max_retries,
            "retry_base_delay_seconds": self.retry_base_delay_seconds,
        }
