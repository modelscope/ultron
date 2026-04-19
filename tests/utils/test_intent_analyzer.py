# Copyright (c) ModelScope Contributors. All rights reserved.
import unittest
from unittest.mock import MagicMock

from ultron.utils.intent_analyzer import IntentAnalyzer


class TestIntentAnalyzer(unittest.TestCase):
    def test_empty_query(self):
        ia = IntentAnalyzer(llm_service=None)
        self.assertEqual(ia.analyze(""), [""])

    def test_whitespace_only_query(self):
        ia = IntentAnalyzer(llm_service=None)
        result = ia.analyze("   ")
        self.assertEqual(len(result), 1)

    def test_no_llm_returns_original(self):
        ia = IntentAnalyzer(llm_service=None)
        self.assertEqual(ia.analyze("  fix pip  "), ["fix pip"])

    def test_dedup(self):
        out = IntentAnalyzer._dedup(["A", "a", "b", "A"])
        self.assertEqual(out, ["A", "b"])

    def test_dedup_empty(self):
        self.assertEqual(IntentAnalyzer._dedup([]), [])

    def test_dedup_preserves_first_spelling(self):
        out = IntentAnalyzer._dedup(["Hello", "hello", "HELLO"])
        self.assertEqual(out, ["Hello"])

    def test_llm_inserts_original_first(self):
        llm = MagicMock()
        llm.is_available = True
        llm.call.return_value = '["paraphrase"]'
        llm.dashscope_user_messages.return_value = []
        llm.parse_json_response.return_value = ["other"]
        ia = IntentAnalyzer(llm_service=llm)
        queries = ia.analyze("Original Q")
        self.assertEqual(queries[0].lower(), "original q")

    def test_llm_unavailable_falls_back(self):
        llm = MagicMock()
        llm.is_available = False
        ia = IntentAnalyzer(llm_service=llm)
        result = ia.analyze("my query")
        self.assertEqual(result, ["my query"])

    def test_llm_call_failure_falls_back(self):
        llm = MagicMock()
        llm.is_available = True
        llm.call.return_value = None
        llm.dashscope_user_messages.return_value = []
        ia = IntentAnalyzer(llm_service=llm)
        result = ia.analyze("my query")
        self.assertEqual(result, ["my query"])

    def test_llm_non_list_response_falls_back(self):
        llm = MagicMock()
        llm.is_available = True
        llm.call.return_value = '{"not": "a list"}'
        llm.dashscope_user_messages.return_value = []
        llm.parse_json_response.return_value = {"not": "a list"}
        ia = IntentAnalyzer(llm_service=llm)
        result = ia.analyze("my query")
        self.assertEqual(result, ["my query"])

    def test_llm_returns_multiple_queries(self):
        llm = MagicMock()
        llm.is_available = True
        llm.dashscope_user_messages.return_value = []
        llm.call.return_value = '["my query", "paraphrase 1", "paraphrase 2"]'
        llm.parse_json_response.return_value = ["my query", "paraphrase 1", "paraphrase 2"]
        ia = IntentAnalyzer(llm_service=llm)
        result = ia.analyze("my query")
        self.assertGreaterEqual(len(result), 2)
        self.assertEqual(result[0].lower(), "my query")

    def test_llm_exception_falls_back(self):
        llm = MagicMock()
        llm.is_available = True
        llm.dashscope_user_messages.side_effect = RuntimeError("network error")
        ia = IntentAnalyzer(llm_service=llm)
        result = ia.analyze("my query")
        self.assertEqual(result, ["my query"])


if __name__ == "__main__":
    unittest.main()
