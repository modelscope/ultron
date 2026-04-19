# Copyright (c) ModelScope Contributors. All rights reserved.
import unittest

from ultron.utils.skill_parser import SkillParser


class TestSkillParserParse(unittest.TestCase):
    def setUp(self):
        self.parser = SkillParser()

    def _make_skill_md(self, name="Test", description="desc", metadata=None, content="# Body"):
        meta_str = metadata or '{"ultron": {"categories": ["general"]}}'
        return f"---\nname: {name}\ndescription: {description}\nmetadata: {meta_str}\n---\n\n{content}"

    def test_parse_valid_frontmatter(self):
        md = self._make_skill_md()
        fm, body = self.parser.parse_skill_md(md)
        self.assertIsNotNone(fm)
        self.assertEqual(fm.name, "Test")
        self.assertEqual(fm.description, "desc")
        self.assertEqual(body, "# Body")

    def test_parse_no_frontmatter_returns_none(self):
        fm, body = self.parser.parse_skill_md("# Just markdown content")
        self.assertIsNone(fm)
        self.assertEqual(body, "# Just markdown content")

    def test_parse_empty_string(self):
        fm, body = self.parser.parse_skill_md("")
        self.assertIsNone(fm)

    def test_parse_categories_from_metadata(self):
        md = self._make_skill_md(metadata='{"ultron": {"categories": ["web-frontend", "ai-llms"]}}')
        fm, _ = self.parser.parse_skill_md(md)
        self.assertIsNotNone(fm)
        self.assertEqual(fm.categories, ["web-frontend", "ai-llms"])

    def test_parse_complexity_from_metadata(self):
        md = self._make_skill_md(metadata='{"ultron": {"categories": ["general"], "complexity": "high"}}')
        fm, _ = self.parser.parse_skill_md(md)
        self.assertEqual(fm.complexity, "high")

    def test_parse_body_stripped(self):
        md = self._make_skill_md(content="\n\n  # Body with whitespace  \n\n")
        _, body = self.parser.parse_skill_md(md)
        self.assertEqual(body, "# Body with whitespace")

    def test_parse_multiline_body(self):
        content = "# Title\n\n## Section\n\nSome content here."
        md = self._make_skill_md(content=content)
        _, body = self.parser.parse_skill_md(md)
        self.assertIn("## Section", body)

    def test_parse_yaml_value_bool_true(self):
        self.assertTrue(self.parser._parse_yaml_value("true"))
        self.assertTrue(self.parser._parse_yaml_value("True"))

    def test_parse_yaml_value_bool_false(self):
        self.assertFalse(self.parser._parse_yaml_value("false"))
        self.assertFalse(self.parser._parse_yaml_value("FALSE"))

    def test_parse_yaml_value_null(self):
        self.assertIsNone(self.parser._parse_yaml_value("null"))
        self.assertIsNone(self.parser._parse_yaml_value("None"))
        self.assertIsNone(self.parser._parse_yaml_value("~"))

    def test_parse_yaml_value_int(self):
        self.assertEqual(self.parser._parse_yaml_value("42"), 42)

    def test_parse_yaml_value_float(self):
        self.assertAlmostEqual(self.parser._parse_yaml_value("3.14"), 3.14)

    def test_parse_yaml_value_quoted_string(self):
        self.assertEqual(self.parser._parse_yaml_value('"hello world"'), "hello world")
        self.assertEqual(self.parser._parse_yaml_value("'hello world'"), "hello world")

    def test_parse_yaml_value_json_object(self):
        result = self.parser._parse_yaml_value('{"key": "value"}')
        self.assertEqual(result, {"key": "value"})

    def test_parse_yaml_value_json_array(self):
        result = self.parser._parse_yaml_value('["a", "b"]')
        self.assertEqual(result, ["a", "b"])

    def test_parse_yaml_value_empty(self):
        self.assertEqual(self.parser._parse_yaml_value(""), "")

    def test_parse_yaml_value_plain_string(self):
        self.assertEqual(self.parser._parse_yaml_value("hello"), "hello")


class TestSkillParserBuild(unittest.TestCase):
    def setUp(self):
        self.parser = SkillParser()

    def test_build_skill_md_roundtrip(self):
        md = self.parser.build_skill_md(
            name="My Skill",
            description="Does something useful",
            content="# Steps\n\n1. Do this\n2. Do that",
            metadata={"ultron": {"categories": ["general"], "complexity": "medium"}},
        )
        fm, body = self.parser.parse_skill_md(md)
        self.assertIsNotNone(fm)
        self.assertEqual(fm.name, "My Skill")
        self.assertEqual(fm.description, "Does something useful")
        self.assertIn("1. Do this", body)

    def test_build_adds_default_ultron_metadata(self):
        md = self.parser.build_skill_md("N", "D", "content")
        fm, _ = self.parser.parse_skill_md(md)
        self.assertIsNotNone(fm)
        self.assertEqual(fm.categories, ["general"])
        self.assertEqual(fm.complexity, "medium")

    def test_build_adds_default_openclaw_metadata(self):
        md = self.parser.build_skill_md("N", "D", "content")
        self.assertIn("openclaw", md)

    def test_build_preserves_existing_metadata(self):
        md = self.parser.build_skill_md(
            "N", "D", "content",
            metadata={"ultron": {"categories": ["ai-llms"], "complexity": "high"}},
        )
        fm, _ = self.parser.parse_skill_md(md)
        self.assertEqual(fm.categories, ["ai-llms"])
        self.assertEqual(fm.complexity, "high")

    def test_build_with_none_metadata(self):
        md = self.parser.build_skill_md("N", "D", "content", metadata=None)
        self.assertIn("---", md)
        self.assertIn("name: N", md)

    def test_build_chinese_name(self):
        md = self.parser.build_skill_md("错误处理", "处理错误的技能", "# 步骤")
        fm, _ = self.parser.parse_skill_md(md)
        self.assertIsNotNone(fm)
        self.assertEqual(fm.name, "错误处理")


class TestSkillParserSlugify(unittest.TestCase):
    def setUp(self):
        self.parser = SkillParser()

    def test_slugify_basic(self):
        self.assertEqual(self.parser._slugify("Hello World"), "hello-world")

    def test_slugify_special_chars(self):
        self.assertEqual(self.parser._slugify("foo!@#bar"), "foobar")

    def test_slugify_multiple_spaces(self):
        self.assertEqual(self.parser._slugify("a  b  c"), "a-b-c")

    def test_slugify_cjk_preserved(self):
        slug = self.parser._slugify("错误处理")
        self.assertIn("错误处理", slug)

    def test_slugify_empty_returns_unknown(self):
        self.assertEqual(self.parser._slugify(""), "unknown")

    def test_slugify_only_special_chars(self):
        self.assertEqual(self.parser._slugify("!@#$%"), "unknown")


if __name__ == "__main__":
    unittest.main()
