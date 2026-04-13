# Copyright (c) ModelScope Contributors. All rights reserved.
# pylint: disable=protected-access

import json
import os
import unittest
from unittest.mock import MagicMock, patch

from ultron.core import llm_service as llm_mod
from ultron.core.llm_service import LLMService


def _char_tokens(s: str) -> int:
    """Deterministic token count for tests (one token per character)."""
    return len(s)


class TestDashscopeUserMessages(unittest.TestCase):
    """
    LLMService adapter without real DashScope HTTP.

    Static message shape for MultiModalConversation.
    """

    def test_wraps_prompt_as_user_multimodal_content(self):
        msgs = LLMService.dashscope_user_messages("hello")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual(msgs[0]["content"], [{"text": "hello"}])


class TestUserTextTokenBudget(unittest.TestCase):
    """Budget derivation for user-supplied prompt segments."""

    def test_subtracts_overhead_and_reserve(self):
        svc = LLMService(
            max_input_tokens=1000,
            prompt_reserve_tokens=100,
            count_tokens=_char_tokens,
        )

        def overhead(s: str) -> int:
            return 400 if "PREFIX" in s else 0

        svc._count_tokens = overhead
        b = svc.user_text_token_budget("PREFIX")
        self.assertEqual(b, max(1000 - 100 - 400, 256))

    def test_floor_at_256(self):
        svc = LLMService(
            max_input_tokens=300,
            prompt_reserve_tokens=200,
            count_tokens=lambda s: 500,
        )
        self.assertEqual(svc.user_text_token_budget("x"), 256)


class TestParseJsonResponse(unittest.TestCase):
    """parse_json_response fences and fallbacks."""

    def setUp(self):
        self.svc = LLMService(count_tokens=_char_tokens)

    def test_plain_array(self):
        r = self.svc.parse_json_response('[{"a": 1}]')
        self.assertEqual(r, [{"a": 1}])

    def test_json_code_fence(self):
        raw = 'prefix\n```json\n[{"x": true}]\n```\nsuffix'
        r = self.svc.parse_json_response(raw)
        self.assertEqual(r, [{"x": True}])

    def test_generic_fence(self):
        raw = "```\n{\"k\": \"v\"}\n```"
        r = self.svc.parse_json_response(raw, expect_array=False)
        self.assertEqual(r, {"k": "v"})

    def test_bracket_slice_when_extra_text(self):
        raw = 'noise {"a": 1} trail'
        r = self.svc.parse_json_response(raw, expect_array=False)
        self.assertEqual(r, {"a": 1})

    def test_array_with_trailing_prose_containing_brackets(self):
        """rindex(']') must not grab a later ] in commentary after valid JSON."""
        raw = '[{"a": 1, "tags": ["x"]}] see also [note] and [refs]'
        r = self.svc.parse_json_response(raw)
        self.assertEqual(r, [{"a": 1, "tags": ["x"]}])

    def test_invalid_returns_empty_list_by_default(self):
        r = self.svc.parse_json_response("not json")
        self.assertEqual(r, [])

    def test_invalid_returns_empty_dict_when_expect_object(self):
        r = self.svc.parse_json_response("not json", expect_array=False)
        self.assertEqual(r, {})


class TestGetInfoAndAvailability(unittest.TestCase):
    """get_info and is_available reflect env and HAS_DASHSCOPE."""

    def test_get_info_keys(self):
        svc = LLMService(
            model="m1",
            api_url="https://example.com",
            count_tokens=_char_tokens,
        )
        info = svc.get_info()
        self.assertEqual(info["model"], "m1")
        self.assertEqual(info["api_url"], "https://example.com")
        self.assertIn("is_available", info)
        self.assertIn("has_dashscope", info)
        self.assertEqual(info["max_input_tokens"], 200_000)
        self.assertEqual(info["prompt_reserve_tokens"], 8192)
        self.assertEqual(info["max_retries"], 2)
        self.assertEqual(info["retry_base_delay_seconds"], 1.0)


class TestCallRetries(unittest.TestCase):
    """call retries on failure then returns text from a later attempt."""

    @patch.object(llm_mod, "HAS_DASHSCOPE", True)
    @patch("ultron.core.llm_service.time.sleep")
    @patch("ultron.core.llm_service.dashscope.MultiModalConversation.call")
    def test_retries_then_succeeds(self, mock_call, _sleep):
        svc = LLMService(
            count_tokens=_char_tokens,
            max_retries=2,
            retry_base_delay_seconds=0.01,
        )
        bad = MagicMock()
        bad.output = None
        good = MagicMock()
        good.output = {
            "choices": [
                {"message": {"content": [{"text": '{"ok": true}'}]}},
            ],
        }
        mock_call.side_effect = [RuntimeError("timeout"), bad, good]

        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "k"}):
            text = svc.call(LLMService.dashscope_user_messages("hi"))

        self.assertEqual(text, '{"ok": true}')
        self.assertEqual(mock_call.call_count, 3)

    @patch.object(llm_mod, "HAS_DASHSCOPE", True)
    @patch("ultron.core.llm_service.time.sleep")
    @patch("ultron.core.llm_service.dashscope.MultiModalConversation.call")
    def test_all_attempts_fail_returns_none(self, mock_call, _sleep):
        svc = LLMService(
            count_tokens=_char_tokens,
            max_retries=2,
            retry_base_delay_seconds=0.01,
        )
        mock_call.side_effect = RuntimeError("down")

        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "k"}):
            text = svc.call(LLMService.dashscope_user_messages("hi"))

        self.assertIsNone(text)
        self.assertEqual(mock_call.call_count, 3)


class TestCallWithoutDashscope(unittest.TestCase):
    """call short-circuits when dashscope or API key is missing."""

    def test_returns_none_when_no_dashscope(self):
        svc = LLMService(count_tokens=_char_tokens)
        with patch.object(llm_mod, "HAS_DASHSCOPE", False):
            self.assertIsNone(svc.call([]))

    @patch.object(llm_mod, "HAS_DASHSCOPE", True)
    def test_returns_none_without_api_key(self):
        svc = LLMService(count_tokens=_char_tokens)
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(svc.call([]))


if __name__ == "__main__":
    unittest.main()
