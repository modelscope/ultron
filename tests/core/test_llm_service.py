# Copyright (c) ModelScope Contributors. All rights reserved.
# pylint: disable=protected-access

import json
import os
import unittest
from unittest.mock import MagicMock, patch

from ultron.core import llm_service as llm_mod
from ultron.core.llm_service import LLMService, _parse_first_json_value


def _char_tokens(s: str) -> int:
    return len(s)


class TestParseFirstJsonValue(unittest.TestCase):
    def test_object(self):
        self.assertEqual(_parse_first_json_value('{"a": 1}'), {"a": 1})

    def test_array(self):
        self.assertEqual(_parse_first_json_value('[1, 2]'), [1, 2])

    def test_leading_noise(self):
        self.assertEqual(_parse_first_json_value('noise {"k": "v"}'), {"k": "v"})

    def test_no_json_returns_none(self):
        self.assertIsNone(_parse_first_json_value("no json here"))

    def test_empty_string_returns_none(self):
        self.assertIsNone(_parse_first_json_value(""))

    def test_stops_at_first_complete_value(self):
        result = _parse_first_json_value('[1, 2] [3, 4]')
        self.assertEqual(result, [1, 2])


class TestUserMessages(unittest.TestCase):
    def test_wraps_prompt_as_user_content(self):
        msgs = LLMService.user_messages("hello")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual(msgs[0]["content"], "hello")

    def test_dashscope_user_messages_alias(self):
        msgs = LLMService.dashscope_user_messages("test")
        self.assertEqual(msgs, LLMService.user_messages("test"))

    def test_empty_prompt(self):
        msgs = LLMService.user_messages("")
        self.assertEqual(msgs[0]["content"], "")


class TestUserTextTokenBudget(unittest.TestCase):
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

    def test_normal_budget(self):
        svc = LLMService(
            max_input_tokens=10000,
            prompt_reserve_tokens=500,
            count_tokens=lambda s: 100,
        )
        b = svc.user_text_token_budget("prompt")
        self.assertEqual(b, 10000 - 500 - 100)


class TestParseJsonResponse(unittest.TestCase):
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
        raw = '[{"a": 1, "tags": ["x"]}] see also [note] and [refs]'
        r = self.svc.parse_json_response(raw)
        self.assertEqual(r, [{"a": 1, "tags": ["x"]}])

    def test_invalid_returns_empty_list_by_default(self):
        r = self.svc.parse_json_response("not json")
        self.assertEqual(r, [])

    def test_invalid_returns_empty_dict_when_expect_object(self):
        r = self.svc.parse_json_response("not json", expect_array=False)
        self.assertEqual(r, {})

    def test_nested_json(self):
        raw = '{"outer": {"inner": [1, 2, 3]}}'
        r = self.svc.parse_json_response(raw, expect_array=False)
        self.assertEqual(r["outer"]["inner"], [1, 2, 3])

    def test_plain_object(self):
        r = self.svc.parse_json_response('{"key": "value"}', expect_array=False)
        self.assertEqual(r, {"key": "value"})


class TestGetInfoAndAvailability(unittest.TestCase):
    def test_get_info_keys(self):
        svc = LLMService(
            model="m1",
            base_url="https://example.com/v1",
            count_tokens=_char_tokens,
        )
        info = svc.get_info()
        self.assertEqual(info["model"], "m1")
        self.assertEqual(info["base_url"], "https://example.com/v1")
        self.assertIn("is_available", info)
        self.assertIn("has_openai", info)
        self.assertEqual(info["max_input_tokens"], 200_000)
        self.assertEqual(info["prompt_reserve_tokens"], 8192)
        self.assertEqual(info["max_retries"], 2)
        self.assertEqual(info["retry_base_delay_seconds"], 1.0)

    def test_is_available_no_key(self):
        svc = LLMService(count_tokens=_char_tokens)
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(svc.is_available)

    def test_is_available_with_key(self):
        with patch.object(llm_mod, "HAS_OPENAI", True):
            with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test-key"}):
                svc = LLMService(count_tokens=_char_tokens)
                self.assertTrue(svc.is_available)

    def test_resolved_api_key_from_env(self):
        svc = LLMService(count_tokens=_char_tokens)
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "env-key"}):
            self.assertEqual(svc._resolved_api_key(), "env-key")

    def test_resolved_api_key_from_constructor(self):
        svc = LLMService(api_key="ctor-key", count_tokens=_char_tokens)
        self.assertEqual(svc._resolved_api_key(), "ctor-key")

    def test_resolved_api_key_openai_provider(self):
        svc = LLMService(provider="openai", count_tokens=_char_tokens)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "openai-key"}):
            self.assertEqual(svc._resolved_api_key(), "openai-key")


class TestCallRetries(unittest.TestCase):
    @patch.object(llm_mod, "HAS_OPENAI", True)
    @patch("ultron.core.llm_service.OpenAI")
    @patch("ultron.core.llm_service.time.sleep")
    def test_retries_then_succeeds(self, _sleep, mock_openai):
        svc = LLMService(
            count_tokens=_char_tokens,
            max_retries=2,
            retry_base_delay_seconds=0.01,
        )
        client = MagicMock()
        bad = MagicMock(choices=[])
        good_msg = MagicMock()
        good_msg.content = '{"ok": true}'
        good_choice = MagicMock(message=good_msg)
        good = MagicMock(choices=[good_choice])
        client.chat.completions.create.side_effect = [RuntimeError("timeout"), bad, good]
        mock_openai.return_value = client

        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "k"}):
            text = svc.call(LLMService.user_messages("hi"))

        self.assertEqual(text, '{"ok": true}')
        self.assertEqual(client.chat.completions.create.call_count, 3)

    @patch.object(llm_mod, "HAS_OPENAI", True)
    @patch("ultron.core.llm_service.OpenAI")
    @patch("ultron.core.llm_service.time.sleep")
    def test_all_attempts_fail_returns_none(self, _sleep, mock_openai):
        svc = LLMService(
            count_tokens=_char_tokens,
            max_retries=2,
            retry_base_delay_seconds=0.01,
        )
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("down")
        mock_openai.return_value = client

        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "k"}):
            text = svc.call(LLMService.user_messages("hi"))

        self.assertIsNone(text)
        self.assertEqual(client.chat.completions.create.call_count, 3)

    @patch.object(llm_mod, "HAS_OPENAI", True)
    @patch("ultron.core.llm_service.OpenAI")
    @patch("ultron.core.llm_service.time.sleep")
    def test_zero_retries_single_attempt(self, _sleep, mock_openai):
        svc = LLMService(count_tokens=_char_tokens, max_retries=0)
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("fail")
        mock_openai.return_value = client

        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "k"}):
            text = svc.call(LLMService.user_messages("hi"))

        self.assertIsNone(text)
        self.assertEqual(client.chat.completions.create.call_count, 1)


class TestCallWithoutOpenAI(unittest.TestCase):
    def test_returns_none_when_no_openai(self):
        svc = LLMService(count_tokens=_char_tokens)
        with patch.object(llm_mod, "HAS_OPENAI", False):
            self.assertIsNone(svc.call([]))

    @patch.object(llm_mod, "HAS_OPENAI", True)
    def test_returns_none_without_api_key(self):
        svc = LLMService(count_tokens=_char_tokens)
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(svc.call([]))


class TestMessageTextFromResponse(unittest.TestCase):
    def setUp(self):
        self.svc = LLMService(count_tokens=_char_tokens)

    def test_extracts_content(self):
        msg = MagicMock()
        msg.content = "hello"
        choice = MagicMock(message=msg)
        resp = MagicMock(choices=[choice])
        self.assertEqual(self.svc._message_text_from_response(resp), "hello")

    def test_none_response(self):
        self.assertIsNone(self.svc._message_text_from_response(None))

    def test_empty_choices(self):
        resp = MagicMock(choices=[])
        self.assertIsNone(self.svc._message_text_from_response(resp))

    def test_non_string_content_returns_none(self):
        msg = MagicMock()
        msg.content = 42
        choice = MagicMock(message=msg)
        resp = MagicMock(choices=[choice])
        self.assertIsNone(self.svc._message_text_from_response(resp))


if __name__ == "__main__":
    unittest.main()
