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


if __name__ == "__main__":
    unittest.main()
