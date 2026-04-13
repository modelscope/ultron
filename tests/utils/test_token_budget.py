# Copyright (c) ModelScope Contributors. All rights reserved.
import unittest

from ultron.utils.token_budget import (
    join_messages_full_text,
    join_messages_lines_within_token_budget,
    split_messages_into_token_windows,
    truncate_text_to_token_limit,
)


def _char_tokens(s: str) -> int:
    return len(s)


class TestTruncateText(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(truncate_text_to_token_limit("", 10, _char_tokens), "")

    def test_no_truncation(self):
        self.assertEqual(truncate_text_to_token_limit("abc", 10, _char_tokens), "abc")

    def test_truncates_unicode_safe(self):
        text = "α" * 100
        out = truncate_text_to_token_limit(text, 10, _char_tokens)
        self.assertLessEqual(_char_tokens(out), 10)
        # Truncated output should end with ellipsis marker
        self.assertTrue(out.endswith("…"))
        # The prefix before the ellipsis must come from the original text
        self.assertTrue(text.startswith(out[:-1]))


class TestJoinMessages(unittest.TestCase):
    def test_join_full(self):
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "yo"},
        ]
        s = join_messages_full_text(msgs)
        self.assertIn("[user]: hi", s)
        self.assertIn("[assistant]: yo", s)

    def test_budget_stops(self):
        msgs = [
            {"role": "user", "content": "aaaa"},
            {"role": "user", "content": "bbbb"},
        ]
        s = join_messages_lines_within_token_budget(msgs, 12, _char_tokens)
        self.assertLessEqual(_char_tokens(s), 12)


class TestSplitWindows(unittest.TestCase):
    def test_single_chunk(self):
        msgs = [{"role": "user", "content": "x"}]
        chunks = split_messages_into_token_windows(msgs, 100, _char_tokens)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], msgs)

    def test_splits_large_batch(self):
        msgs = [
            {"role": "user", "content": "a" * 30},
            {"role": "user", "content": "b" * 30},
        ]
        chunks = split_messages_into_token_windows(msgs, 40, _char_tokens)
        self.assertGreaterEqual(len(chunks), 1)
        total_lines = join_messages_full_text([m for c in chunks for m in c])
        self.assertIn("aaaa", total_lines)


if __name__ == "__main__":
    unittest.main()
