# Copyright (c) ModelScope Contributors. All rights reserved.
import unittest
from unittest.mock import MagicMock

from ultron.utils.intent_analyzer import IntentAnalyzer


class TestIntentAnalyzer(unittest.TestCase):
    def test_empty_query(self):
        ia = IntentAnalyzer(llm_service=None)
        self.assertEqual(ia.analyze(""), [""])

    def test_no_llm_returns_original(self):
        ia = IntentAnalyzer(llm_service=None)
        self.assertEqual(ia.analyze("  fix pip  "), ["fix pip"])

    def test_dedup(self):
        out = IntentAnalyzer._dedup(["A", "a", "b", "A"])
        self.assertEqual(out, ["A", "b"])

    def test_llm_inserts_original_first(self):
        llm = MagicMock()
        llm.is_available = True
        llm.call.return_value = '["paraphrase"]'
        llm.dashscope_user_messages.return_value = []
        llm.parse_json_response.return_value = ["other"]
        ia = IntentAnalyzer(llm_service=llm)
        queries = ia.analyze("Original Q")
        self.assertEqual(queries[0].lower(), "original q")


if __name__ == "__main__":
    unittest.main()
