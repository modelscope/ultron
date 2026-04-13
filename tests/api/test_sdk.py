# Copyright (c) ModelScope Contributors. All rights reserved.
import unittest

from ultron.api.sdk import Ultron


class TestUltronHelpers(unittest.TestCase):
    """
    Ultron SDK helpers that do not require a full instance initialisation.
    """

    def test_increment_version(self):
        u = object.__new__(Ultron)
        self.assertEqual(u._increment_version("2.1.3"), "2.1.4")

    def test_increment_version_fallback(self):
        u = object.__new__(Ultron)
        self.assertEqual(u._increment_version("not-a-version"), "1.0.1")


if __name__ == "__main__":
    unittest.main()
