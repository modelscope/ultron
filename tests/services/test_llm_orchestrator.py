# Copyright (c) ModelScope Contributors. All rights reserved.
# pylint: disable=protected-access

import json
import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from ultron.core.llm_service import LLMService
from ultron.utils.llm_orchestrator import LLMOrchestrator


def _char_tokens(s: str) -> int:
    """Deterministic token count for tests (one token per character)."""
    return len(s)


def _make_orchestrator() -> LLMOrchestrator:
    svc = LLMService(count_tokens=_char_tokens)
    return LLMOrchestrator(svc)


class TestPrepareConversationText(unittest.TestCase):
    """
    LLMOrchestrator without real DashScope HTTP.

    Covers prepare_conversation_text_for_memory_extraction.
    """

    def setUp(self):
        self.orch = _make_orchestrator()

    def test_explicit_max_tokens_has_256_minimum_floor(self):
        """Values below 256 are lifted to 256 (chunk budget safety)."""
        messages = [
            {"role": "user", "content": "a" * 50},
            {"role": "assistant", "content": "b" * 50},
        ]
        out = self.orch.prepare_conversation_text_for_memory_extraction(
            messages, max_conversation_tokens=60
        )
        self.assertLessEqual(_char_tokens(out), 256)
        self.assertIn("[user]:", out)
        self.assertIn("[assistant]:", out)

    def test_explicit_max_truncates_single_long_message(self):
        messages = [{"role": "user", "content": "z" * 500}]
        out = self.orch.prepare_conversation_text_for_memory_extraction(
            messages, max_conversation_tokens=300
        )
        self.assertLessEqual(_char_tokens(out), 300)
        self.assertTrue(out.startswith("[user]: "))

    def test_derives_budget_from_prompt_when_max_not_given(self):
        messages = [{"role": "user", "content": "hi"}]
        out = self.orch.prepare_conversation_text_for_memory_extraction(messages)
        self.assertIn("[user]: hi", out)


class TestExtractMemoriesMocked(unittest.TestCase):
    """extract_memories_from_text with mocked call."""

    def setUp(self):
        self.orch = _make_orchestrator()

    def test_empty_returns_empty_when_no_llm_reply(self):
        self.orch.llm.call = MagicMock(return_value=None)
        self.assertEqual(self.orch.extract_memories_from_text("any"), [])

    def test_parses_json_array(self):
        payload = [{"content": "c", "context": "", "resolution": "", "tags": ["t"]}]
        self.orch.llm.call = MagicMock(return_value=json.dumps(payload))
        out = self.orch.extract_memories_from_text("body")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["content"], "c")


class TestSummarizeForL0L1Mocked(unittest.TestCase):
    """summarize_for_l0_l1 with mocked call."""

    def setUp(self):
        self.orch = _make_orchestrator()

    def test_none_when_call_fails(self):
        self.orch.llm.call = MagicMock(return_value=None)
        self.assertIsNone(
            self.orch.summarize_for_l0_l1("a", "b", "c", l0_max_tokens=8, l1_max_tokens=8)
        )

    def test_truncates_output_to_token_caps(self):
        long0 = "x" * 100
        long1 = "y" * 100
        self.orch.llm.call = MagicMock(
            return_value=json.dumps({"summary_l0": long0, "overview_l1": long1})
        )
        out = self.orch.summarize_for_l0_l1(
            "c", "", "", l0_max_tokens=10, l1_max_tokens=20
        )
        self.assertIsNotNone(out)
        self.assertEqual(len(out["summary_l0"]), 10)
        self.assertEqual(len(out["overview_l1"]), 20)


class TestMergeMemoriesMocked(unittest.TestCase):
    """merge_memories with mocked call."""

    def setUp(self):
        self.orch = _make_orchestrator()

    def test_none_when_missing_content(self):
        self.orch.llm.call = MagicMock(return_value=json.dumps({"context": "x", "resolution": ""}))
        self.assertIsNone(
            self.orch.merge_memories("a", "b", "c", "d", "e", "f", max_field_tokens=0)
        )

    def test_returns_merged_fields(self):
        self.orch.llm.call = MagicMock(
            return_value=json.dumps(
                {"content": "merged", "context": "ctx", "resolution": "res"}
            )
        )
        out = self.orch.merge_memories("a", "b", "c", "d", "e", "f")
        self.assertEqual(out["content"], "merged")


class TestGenerateSkillContentMocked(unittest.TestCase):
    """generate_skill_content with mocked call."""

    def setUp(self):
        self.orch = _make_orchestrator()

    def test_requires_content_in_response(self):
        self.orch.llm.call = MagicMock(return_value=json.dumps({"name": "n", "description": "d"}))
        self.assertIsNone(self.orch.generate_skill_content("a", "b", "c"))

    def test_optional_related_and_contributions(self):
        self.orch.llm.call = MagicMock(
            return_value=json.dumps(
                {
                    "name": "my-skill",
                    "description": "desc",
                    "content": "## Body",
                }
            )
        )
        out = self.orch.generate_skill_content(
            "pc",
            "pct",
            "pres",
            related_memories=[{"content": "rel"}],
            contributions=[{"resolution": "alt"}],
        )
        self.assertEqual(out["name"], "my-skill")
        self.assertIn("## Body", out["content"])


class TestClassify(unittest.TestCase):
    """classify_memory_type availability and parsing."""

    def setUp(self):
        self.orch = _make_orchestrator()

    def test_returns_none_when_service_unavailable(self):
        with patch.object(LLMService, "is_available", new_callable=PropertyMock, return_value=False):
            self.assertIsNone(self.orch.classify_memory_type("x"))

    @patch.object(LLMService, "is_available", new_callable=PropertyMock, return_value=True)
    def test_valid_type_lowercased(self, _mock_avail):
        self.orch.llm.call = MagicMock(return_value='{"memory_type": "PATTERN"}')
        self.assertEqual(self.orch.classify_memory_type("c"), "pattern")

    @patch.object(LLMService, "is_available", new_callable=PropertyMock, return_value=True)
    def test_unknown_type_returns_none(self, _mock_avail):
        self.orch.llm.call = MagicMock(return_value='{"memory_type": "unknown"}')
        self.assertIsNone(self.orch.classify_memory_type("c"))


if __name__ == "__main__":
    unittest.main()
