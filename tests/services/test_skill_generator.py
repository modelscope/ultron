# Copyright (c) ModelScope Contributors. All rights reserved.
import unittest
from datetime import datetime, timedelta

from ultron.services.skill.skill_generator import SkillGeneratorService


class TestSkillGeneratorStatics(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(SkillGeneratorService._slugify("Hello World!"), "hello-world")
        self.assertEqual(SkillGeneratorService._slugify("测试_ABC"), "测试-abc")

    def test_increment_version(self):
        self.assertEqual(SkillGeneratorService._increment_version("1.0.9"), "1.0.10")

    def test_calculate_hotness(self):
        recent = datetime.now() - timedelta(hours=1)
        h = SkillGeneratorService._calculate_hotness(recent.isoformat())
        self.assertGreater(h, 0.9)


if __name__ == "__main__":
    unittest.main()
