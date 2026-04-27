# Copyright (c) ModelScope Contributors. All rights reserved.
import json
import unittest

from ultron.utils.jsonl_session_messages import (
    detect_jsonl_session_format,
    expand_parsed_messages_to_plain,
    message_body_for_llm,
    parse_agent_jsonl_lines,
    parse_jsonl_lines_for_trajectory,
)
from ultron.utils.token_budget import compute_segment_fingerprint


class TestJsonlSessionMessages(unittest.TestCase):
    def test_detect_format(self):
        openai_lines = [json.dumps({"role": "user", "content": "hi"})]
        self.assertEqual(detect_jsonl_session_format(openai_lines), "openai")
        anth_lines = [
            json.dumps(
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "x"}, {"type": "tool_use", "id": "1", "name": "read", "input": {}}],
                }
            )
        ]
        self.assertEqual(detect_jsonl_session_format(anth_lines), "anthropic")

    def test_force_openai_skips_block_expansion(self):
        line = json.dumps(
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "only"}],
            }
        )
        native = parse_agent_jsonl_lines([line], session_format="openai")
        self.assertEqual(native[0]["role"], "assistant")
        self.assertIn('"type": "text"', native[0]["content"])

    def test_invalid_session_format(self):
        with self.assertRaises(ValueError):
            parse_agent_jsonl_lines([], session_format="other")  # type: ignore[arg-type]

    def test_skips_metadata_and_unknown_role(self):
        lines = [
            json.dumps({"_type": "metadata", "key": "x"}),
            json.dumps({"role": "user", "content": "hi"}),
            json.dumps({"role": "developer", "content": "nope"}),
        ]
        raw = parse_agent_jsonl_lines(lines)
        self.assertEqual(len(raw), 1)
        self.assertEqual(raw[0]["role"], "user")

    def test_nanobot_style_tool_round_native(self):
        lines = [
            json.dumps({"role": "user", "content": "weather?"}),
            json.dumps(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}],
                    "reasoning_content": "read skill",
                }
            ),
            json.dumps(
                {
                    "role": "tool",
                    "tool_call_id": "c1",
                    "name": "read_file",
                    "content": "SKILL body",
                }
            ),
            json.dumps({"role": "assistant", "content": "Which city?"}),
        ]
        native = parse_jsonl_lines_for_trajectory(lines)
        self.assertEqual(len(native), 4)
        self.assertEqual(native[0], {"role": "user", "content": "weather?"})
        self.assertEqual(native[1]["role"], "assistant")
        self.assertEqual(native[1]["content"], "")
        self.assertEqual(native[1]["reasoning_content"], "read skill")
        self.assertIsInstance(native[1]["tool_calls"], list)
        self.assertEqual(native[2]["role"], "tool")
        self.assertEqual(native[2]["name"], "read_file")
        self.assertEqual(native[3]["content"], "Which city?")
        body = message_body_for_llm(native[1])
        self.assertIn("[reasoning]", body)
        self.assertIn("[tool_calls]", body)

    def test_system_preserved(self):
        lines = [json.dumps({"role": "system", "content": "You are helpful."})]
        native = parse_jsonl_lines_for_trajectory(lines)
        self.assertEqual(native, [{"role": "system", "content": "You are helpful."}])

    def test_empty_tool_row_kept_in_trajectory(self):
        """Degenerate tool line (no name, id, content) is kept; indices stay aligned."""
        lines = [
            json.dumps({"role": "user", "content": "x"}),
            json.dumps(
                {
                    "role": "tool",
                    "content": "",
                    "name": "",
                    "tool_call_id": "",
                }
            ),
            json.dumps({"role": "assistant", "content": "ok"}),
        ]
        native = parse_jsonl_lines_for_trajectory(lines)
        self.assertEqual(len(native), 3)
        self.assertEqual(native[1]["role"], "tool")
        self.assertEqual(message_body_for_llm(native[1]), "")

    def test_fingerprint_includes_tool_calls_not_only_merged_text(self):
        a = [
            {
                "role": "assistant",
                "content": "",
                "reasoning_content": "",
                "tool_calls": [{"id": "1"}],
            }
        ]
        b = [
            {
                "role": "assistant",
                "content": "",
                "reasoning_content": "",
                "tool_calls": [{"id": "2"}],
            }
        ]
        self.assertNotEqual(compute_segment_fingerprint(a), compute_segment_fingerprint(b))

    def test_expand_plain_still_works(self):
        lines = [json.dumps({"role": "user", "content": "x"})]
        plain = expand_parsed_messages_to_plain(parse_agent_jsonl_lines(lines))
        self.assertEqual(plain, [{"role": "user", "content": "x"}])

    def test_anthropic_user_tool_result_round_trip_native(self):
        lines = [
            json.dumps(
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "call tool"}],
                }
            ),
            json.dumps(
                {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "plan"},
                        {
                            "type": "tool_use",
                            "id": "tu1",
                            "name": "read",
                            "input": {"path": "/x"},
                        },
                    ],
                }
            ),
            json.dumps(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tu1",
                            "content": "file body",
                            "is_error": False,
                        }
                    ],
                }
            ),
        ]
        native = parse_jsonl_lines_for_trajectory(lines)
        self.assertEqual(native[0], {"role": "user", "content": "call tool"})
        self.assertEqual(native[1]["role"], "assistant")
        self.assertEqual(native[1]["reasoning_content"], "plan")
        self.assertIsInstance(native[1]["tool_calls"], list)
        self.assertEqual(native[1]["tool_calls"][0]["function"]["name"], "read")
        self.assertEqual(native[2]["role"], "tool")
        self.assertEqual(native[2]["tool_call_id"], "tu1")
        self.assertEqual(native[2]["content"], "file body")

    def test_stop_reason_preserved_not_in_llm_body(self):
        line = json.dumps(
            {
                "role": "assistant",
                "stop_reason": "tool_use",
                "content": [
                    {"type": "thinking", "thinking": "x"},
                    {"type": "text", "text": "hi"},
                ],
            }
        )
        native = parse_jsonl_lines_for_trajectory([line])[0]
        self.assertEqual(native.get("stop_reason"), "tool_use")
        body = message_body_for_llm(native)
        self.assertNotIn("stop_reason", body)
        self.assertIn("[reasoning]", body)
        self.assertIn("hi", body)

    def test_fingerprint_includes_stop_reason(self):
        base = {
            "role": "assistant",
            "content": "a",
            "reasoning_content": "",
            "tool_calls": None,
        }
        a = [{**base, "stop_reason": "end_turn"}]
        b = [{**base, "stop_reason": "tool_use"}]
        self.assertNotEqual(compute_segment_fingerprint(a), compute_segment_fingerprint(b))

    def test_anthropic_text_only_list_same_as_string_path(self):
        a = parse_jsonl_lines_for_trajectory(
            [json.dumps({"role": "user", "content": [{"type": "text", "text": "  hi  "}]})]
        )
        b = parse_jsonl_lines_for_trajectory([json.dumps({"role": "user", "content": "hi"})])
        self.assertEqual(a, b)

    def test_anthropic_user_row_text_then_tool_result_order(self):
        line = json.dumps(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "pre"},
                    {"type": "tool_result", "tool_use_id": "x", "content": "out"},
                ],
            }
        )
        native = parse_jsonl_lines_for_trajectory([line])
        self.assertEqual(native[0]["role"], "user")
        self.assertEqual(native[0]["content"], "pre")
        self.assertEqual(native[1]["role"], "tool")
        self.assertEqual(native[1]["tool_call_id"], "x")


if __name__ == "__main__":
    unittest.main()
