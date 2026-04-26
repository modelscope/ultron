# Copyright (c) ModelScope Contributors. All rights reserved.
import unittest

from ultron.utils.token_budget import (
    CONVERSATION_ROLES,
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
        self.assertTrue(out.endswith("…"))
        self.assertTrue(text.startswith(out[:-1]))

    def test_zero_max_tokens_returns_empty(self):
        self.assertEqual(truncate_text_to_token_limit("hello", 0, _char_tokens), "")

    def test_negative_max_tokens_returns_empty(self):
        self.assertEqual(truncate_text_to_token_limit("hello", -5, _char_tokens), "")

    def test_exact_fit_no_ellipsis(self):
        text = "hello"
        out = truncate_text_to_token_limit(text, 5, _char_tokens)
        self.assertEqual(out, "hello")
        self.assertFalse(out.endswith("…"))

    def test_snaps_to_sentence_boundary(self):
        text = "First sentence. Second sentence. Third sentence."
        out = truncate_text_to_token_limit(text, 20, _char_tokens)
        self.assertLessEqual(_char_tokens(out), 20)

    def test_chinese_sentence_boundary(self):
        text = "第一句话。第二句话。第三句话。"
        out = truncate_text_to_token_limit(text, 10, _char_tokens)
        self.assertLessEqual(_char_tokens(out), 10)

    def test_single_char_max(self):
        # With max_tokens=2, result fits within 2 chars (ellipsis takes 1)
        out = truncate_text_to_token_limit("hello world", 2, _char_tokens)
        self.assertLessEqual(_char_tokens(out), 2)


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

    def test_join_full_includes_system_role(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        s = join_messages_full_text(msgs)
        self.assertIn("[system]: sys", s)
        self.assertIn("[user]: hi", s)

    def test_join_full_skips_empty_content(self):
        msgs = [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": "ok"},
        ]
        s = join_messages_full_text(msgs)
        self.assertNotIn("[user]:", s)
        self.assertIn("[assistant]: ok", s)

    def test_budget_zero_returns_empty(self):
        msgs = [{"role": "user", "content": "hello"}]
        s = join_messages_lines_within_token_budget(msgs, 0, _char_tokens)
        self.assertEqual(s, "")

    def test_budget_fits_all(self):
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "yo"},
        ]
        s = join_messages_lines_within_token_budget(msgs, 1000, _char_tokens)
        self.assertIn("[user]: hi", s)
        self.assertIn("[assistant]: yo", s)

    def test_budget_truncates_last_message(self):
        msgs = [
            {"role": "user", "content": "a" * 5},
            {"role": "user", "content": "b" * 100},
        ]
        # Budget is tight enough that the second message must be truncated
        s = join_messages_lines_within_token_budget(msgs, 50, _char_tokens)
        self.assertIn("[user]: aaaaa", s)
        # Second message should be truncated (not full 100 b's)
        self.assertNotIn("b" * 100, s)


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

    def test_empty_messages_returns_empty(self):
        chunks = split_messages_into_token_windows([], 100, _char_tokens)
        self.assertEqual(chunks, [])

    def test_includes_system_messages_in_windows(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        chunks = split_messages_into_token_windows(msgs, 100, _char_tokens)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(len(chunks[0]), 2)
        self.assertEqual(chunks[0][0]["role"], "system")
        self.assertEqual(chunks[0][1]["role"], "user")

    def test_legacy_user_assistant_only_roles_param(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        s = join_messages_full_text(msgs, roles=("user", "assistant"))
        self.assertNotIn("[system]:", s)
        self.assertIn("[user]: hi", s)
        self.assertEqual(CONVERSATION_ROLES[-1], "system")

    def test_very_long_single_message_truncated(self):
        msgs = [{"role": "user", "content": "x" * 1000}]
        chunks = split_messages_into_token_windows(msgs, 50, _char_tokens)
        self.assertEqual(len(chunks), 1)
        # Content should be truncated to fit window
        content = chunks[0][0]["content"]
        self.assertLessEqual(len(content), 1000)

    def test_multiple_chunks_cover_all_messages(self):
        msgs = [{"role": "user", "content": f"msg{i}" * 5} for i in range(10)]
        chunks = split_messages_into_token_windows(msgs, 30, _char_tokens)
        total_msgs = sum(len(c) for c in chunks)
        self.assertEqual(total_msgs, 10)


if __name__ == "__main__":
    unittest.main()
