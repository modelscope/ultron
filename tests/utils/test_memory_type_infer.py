# Copyright (c) ModelScope Contributors. All rights reserved.
import unittest

from ultron.utils.memory_type_infer import infer_memory_type


class TestInferMemoryType(unittest.TestCase):
    def test_security(self):
        self.assertEqual(infer_memory_type("Discussing CVE-2024-1"), "security")

    def test_error(self):
        self.assertEqual(infer_memory_type("Traceback (most recent call last)"), "error")

    def test_pattern_default(self):
        self.assertEqual(infer_memory_type("Reusable workflow note"), "pattern")

    def test_resolution_field(self):
        self.assertEqual(infer_memory_type("", "", "segmentation fault"), "error")

    def test_context_field(self):
        self.assertEqual(infer_memory_type("", "xss vulnerability found", ""), "security")

    def test_chinese_security(self):
        self.assertEqual(infer_memory_type("发现漏洞，需要修复"), "security")

    def test_chinese_error(self):
        self.assertEqual(infer_memory_type("程序报错，执行失败"), "error")

    def test_error_keywords(self):
        for kw in ("exception:", "error:", "syntaxerror", "typeerror", "valueerror",
                   "keyerror", "attributeerror", "core dumped", "exit code"):
            self.assertEqual(infer_memory_type(kw), "error", msg=f"Expected error for: {kw}")

    def test_security_keywords(self):
        for kw in ("sql injection", "xss", "csrf", "ssrf", "rce", "phishing",
                   "malware", "ransomware", "backdoor"):
            self.assertEqual(infer_memory_type(kw), "security", msg=f"Expected security for: {kw}")

    def test_security_takes_priority_over_error(self):
        # Both security and error keywords present — security wins (checked first)
        self.assertEqual(infer_memory_type("CVE-2024-1 traceback error"), "security")

    def test_empty_all_fields(self):
        self.assertEqual(infer_memory_type("", "", ""), "pattern")

    def test_case_insensitive(self):
        self.assertEqual(infer_memory_type("TRACEBACK (most recent call last)"), "error")
        self.assertEqual(infer_memory_type("SQL INJECTION attack"), "security")


if __name__ == "__main__":
    unittest.main()
