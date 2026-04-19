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
    def setUp(self):
        self.orch = _make_orchestrator()

    def test_explicit_max_tokens_has_256_minimum_floor(self):
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

    def test_empty_messages_returns_empty(self):
        out = self.orch.prepare_conversation_text_for_memory_extraction([])
        self.assertEqual(out.strip(), "")


class TestExtractMemoriesMocked(unittest.TestCase):
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

    def test_non_list_response_returns_empty(self):
        self.orch.llm.call = MagicMock(return_value='{"content": "c"}')
        out = self.orch.extract_memories_from_text("body")
        self.assertEqual(out, [])


class TestSummarizeForL0L1Mocked(unittest.TestCase):
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

    def test_non_dict_response_returns_none(self):
        self.orch.llm.call = MagicMock(return_value='["not", "a", "dict"]')
        out = self.orch.summarize_for_l0_l1("c", "", "")
        self.assertIsNone(out)


class TestMergeMemoriesMocked(unittest.TestCase):
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

    def test_none_when_call_fails(self):
        self.orch.llm.call = MagicMock(return_value=None)
        out = self.orch.merge_memories("a", "b", "c", "d", "e", "f")
        self.assertIsNone(out)

    def test_truncates_fields_when_max_set(self):
        self.orch.llm.call = MagicMock(
            return_value=json.dumps({
                "content": "x" * 200,
                "context": "y" * 200,
                "resolution": "z" * 200,
            })
        )
        out = self.orch.merge_memories("a", "b", "c", "d", "e", "f", max_field_tokens=50)
        self.assertIsNotNone(out)
        self.assertLessEqual(len(out["content"]), 50)


class TestClassify(unittest.TestCase):
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

    @patch.object(LLMService, "is_available", new_callable=PropertyMock, return_value=True)
    def test_call_failure_returns_none(self, _mock_avail):
        self.orch.llm.call = MagicMock(return_value=None)
        self.assertIsNone(self.orch.classify_memory_type("c"))

    @patch.object(LLMService, "is_available", new_callable=PropertyMock, return_value=True)
    def test_all_valid_types(self, _mock_avail):
        for t in ("error", "security", "correction", "pattern", "preference", "life"):
            self.orch.llm.call = MagicMock(return_value=json.dumps({"memory_type": t}))
            self.assertEqual(self.orch.classify_memory_type("c"), t)


class TestConfirmMemoryDuplicate(unittest.TestCase):
    def setUp(self):
        self.orch = _make_orchestrator()

    def test_returns_true_when_should_merge(self):
        self.orch.classify_llm.call = MagicMock(
            return_value='{"should_merge": true}'
        )
        self.assertTrue(self.orch.confirm_memory_duplicate("a", "b", "c", "d"))

    def test_returns_false_when_not_merge(self):
        self.orch.classify_llm.call = MagicMock(
            return_value='{"should_merge": false}'
        )
        self.assertFalse(self.orch.confirm_memory_duplicate("a", "b", "c", "d"))

    def test_returns_false_on_call_failure(self):
        self.orch.classify_llm.call = MagicMock(return_value=None)
        self.assertFalse(self.orch.confirm_memory_duplicate("a", "b", "c", "d"))

    def test_returns_false_on_invalid_json(self):
        self.orch.classify_llm.call = MagicMock(return_value="not json")
        self.assertFalse(self.orch.confirm_memory_duplicate("a", "b", "c", "d"))


class TestCrystallizeSkillFromCluster(unittest.TestCase):
    def setUp(self):
        self.orch = _make_orchestrator()

    def _memories(self):
        return [{"id": f"m{i}", "content": f"content {i}", "context": "", "resolution": ""} for i in range(3)]

    def test_returns_none_on_call_failure(self):
        self.orch.llm.call = MagicMock(return_value=None)
        result = self.orch.crystallize_skill_from_cluster(self._memories(), "topic")
        self.assertIsNone(result)

    def test_returns_insufficient_quality(self):
        self.orch.llm.call = MagicMock(return_value='{"quality": "insufficient"}')
        result = self.orch.crystallize_skill_from_cluster(self._memories(), "topic")
        self.assertEqual(result.get("quality"), "insufficient")

    def test_returns_skill_dict(self):
        self.orch.llm.call = MagicMock(
            return_value=json.dumps({
                "name": "my-skill", "description": "desc", "content": "# Skill\n\nsteps"
            })
        )
        result = self.orch.crystallize_skill_from_cluster(self._memories(), "topic")
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "my-skill")

    def test_returns_none_when_no_content(self):
        self.orch.llm.call = MagicMock(
            return_value=json.dumps({"name": "x", "description": "d", "content": ""})
        )
        result = self.orch.crystallize_skill_from_cluster(self._memories())
        self.assertIsNone(result)


class TestRecrystallizeSkill(unittest.TestCase):
    def setUp(self):
        self.orch = _make_orchestrator()

    def _memories(self):
        return [{"id": f"m{i}", "content": f"content {i}", "context": "", "resolution": ""} for i in range(3)]

    def test_returns_none_on_call_failure(self):
        self.orch.llm.call = MagicMock(return_value=None)
        result = self.orch.recrystallize_skill("old content", "1.0.0", self._memories(), 2)
        self.assertIsNone(result)

    def test_returns_unnecessary(self):
        self.orch.llm.call = MagicMock(return_value='{"evolution": "unnecessary"}')
        result = self.orch.recrystallize_skill("old content", "1.0.0", self._memories(), 2)
        self.assertEqual(result.get("evolution"), "unnecessary")

    def test_returns_updated_skill(self):
        self.orch.llm.call = MagicMock(
            return_value=json.dumps({
                "name": "updated-skill", "description": "new desc", "content": "# Updated"
            })
        )
        result = self.orch.recrystallize_skill("old content", "1.0.0", self._memories(), 2)
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "updated-skill")


class TestVerifySkill(unittest.TestCase):
    def setUp(self):
        self.orch = _make_orchestrator()

    def _memories(self):
        return [{"id": "m1", "content": "content", "context": "", "resolution": ""}]

    def test_returns_none_on_call_failure(self):
        self.orch.llm.call = MagicMock(return_value=None)
        result = self.orch.verify_skill("skill content", self._memories())
        self.assertIsNone(result)

    def test_returns_verification_dict(self):
        v = {
            "claims": [], "grounded_in_evidence": 0.9,
            "has_contradiction": False, "workflow_clarity": 0.8,
            "specificity_and_reusability": 0.75,
        }
        self.orch.llm.call = MagicMock(return_value=json.dumps(v))
        result = self.orch.verify_skill("skill content", self._memories())
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["grounded_in_evidence"], 0.9)

    def test_recrystallization_flag_included(self):
        v = {
            "claims": [], "grounded_in_evidence": 0.9,
            "has_contradiction": False, "workflow_clarity": 0.8,
            "specificity_and_reusability": 0.75, "preserves_existing_value": 0.85,
        }
        self.orch.llm.call = MagicMock(return_value=json.dumps(v))
        result = self.orch.verify_skill("skill content", self._memories(), is_recrystallization=True)
        self.assertIn("preserves_existing_value", result)


class TestGenerateClusterTopic(unittest.TestCase):
    def setUp(self):
        self.orch = _make_orchestrator()

    def test_returns_topic_string(self):
        self.orch.llm.call = MagicMock(return_value="error handling patterns")
        memories = [{"summary_l0": "handle errors gracefully"}]
        result = self.orch.generate_cluster_topic(memories)
        self.assertEqual(result, "error handling patterns")

    def test_empty_memories_returns_empty(self):
        result = self.orch.generate_cluster_topic([])
        self.assertEqual(result, "")

    def test_call_failure_returns_empty(self):
        self.orch.llm.call = MagicMock(return_value=None)
        memories = [{"summary_l0": "some summary"}]
        result = self.orch.generate_cluster_topic(memories)
        self.assertEqual(result, "")


class TestFormatMemoriesForPrompt(unittest.TestCase):
    def setUp(self):
        self.orch = _make_orchestrator()

    def test_formats_memories(self):
        memories = [
            {"id": "abc123", "content": "content A", "context": "ctx A", "resolution": "res A"},
            {"id": "def456", "content": "content B", "context": "", "resolution": ""},
        ]
        result = self.orch._format_memories_for_prompt(memories)
        self.assertIn("Experience 1", result)
        self.assertIn("Experience 2", result)
        self.assertIn("content A", result)
        self.assertIn("abc123", result)

    def test_empty_memories_returns_empty(self):
        result = self.orch._format_memories_for_prompt([])
        self.assertEqual(result, "")

    def test_skips_empty_context_and_resolution(self):
        memories = [{"id": "x", "content": "c", "context": "", "resolution": ""}]
        result = self.orch._format_memories_for_prompt(memories)
        self.assertNotIn("Context:", result)
        self.assertNotIn("Resolution:", result)


if __name__ == "__main__":
    unittest.main()

