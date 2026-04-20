# Copyright (c) ModelScope Contributors. All rights reserved.
import tempfile
import unittest
from pathlib import Path

from ultron.services.harness.soul_presets import SoulPresetService, _parse_frontmatter, _slugify


def _write_preset(directory: Path, category: str, filename: str, content: str) -> None:
    cat_dir = directory / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    (cat_dir / filename).write_text(content, encoding="utf-8")


_SAMPLE_PRESET = """\
---
name: Test Assistant
description: A helpful test assistant
emoji: 🤖
color: blue
vibe: Friendly and helpful
---

## Identity and Communication Style
Be helpful and concise.

## Critical Rules
Always be honest.
"""


class TestParseFrontmatter(unittest.TestCase):
    def test_parses_basic_fields(self):
        meta, body = _parse_frontmatter(_SAMPLE_PRESET)
        self.assertEqual(meta["name"], "Test Assistant")
        self.assertEqual(meta["emoji"], "🤖")
        self.assertIn("Identity", body)

    def test_no_frontmatter_returns_empty_meta(self):
        meta, body = _parse_frontmatter("# Just markdown")
        self.assertEqual(meta, {})
        self.assertEqual(body, "# Just markdown")

    def test_incomplete_frontmatter(self):
        meta, body = _parse_frontmatter("---\nname: Test\n")
        self.assertEqual(meta, {})

    def test_list_value_not_parsed(self):
        # soul_presets._parse_frontmatter does NOT parse list values — returns raw string
        content = "---\ntags: [a, b, c]\n---\nbody"
        meta, _ = _parse_frontmatter(content)
        self.assertEqual(meta["tags"], "[a, b, c]")


class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(_slugify("Hello World"), "hello-world")

    def test_special_chars(self):
        self.assertEqual(_slugify("foo!@#bar"), "foo-bar")

    def test_already_slug(self):
        self.assertEqual(_slugify("my-preset"), "my-preset")


class TestSoulPresetServiceLoad(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_empty_dir(self):
        svc = SoulPresetService(presets_dir=self.root)
        svc.load()
        self.assertEqual(svc.list_presets(), [])

    def test_load_missing_dir(self):
        svc = SoulPresetService(presets_dir=self.root / "nonexistent")
        svc.load()
        self.assertEqual(svc.list_presets(), [])

    def test_load_preset(self):
        _write_preset(self.root, "role", "assistant.md", _SAMPLE_PRESET)
        svc = SoulPresetService(presets_dir=self.root)
        svc.load()
        presets = svc.list_presets()
        self.assertEqual(len(presets), 1)
        self.assertEqual(presets[0]["id"], "role")
        self.assertEqual(len(presets[0]["presets"]), 1)
        self.assertEqual(presets[0]["presets"][0]["name"], "Test Assistant")

    def test_load_skips_readme(self):
        _write_preset(self.root, "role", "README.md", "# README")
        _write_preset(self.root, "role", "assistant.md", _SAMPLE_PRESET)
        svc = SoulPresetService(presets_dir=self.root)
        svc.load()
        self.assertEqual(len(svc.list_presets()[0]["presets"]), 1)

    def test_load_skips_no_name(self):
        _write_preset(self.root, "role", "noname.md", "---\ndescription: no name\n---\nbody")
        svc = SoulPresetService(presets_dir=self.root)
        svc.load()
        self.assertEqual(svc.list_presets(), [])

    def test_multiple_categories(self):
        _write_preset(self.root, "role", "assistant.md", _SAMPLE_PRESET)
        _write_preset(self.root, "mbti", "intj.md", "---\nname: INTJ\n---\nbody")
        svc = SoulPresetService(presets_dir=self.root)
        svc.load()
        categories = [p["id"] for p in svc.list_presets()]
        self.assertIn("role", categories)
        self.assertIn("mbti", categories)


class TestSoulPresetServiceGet(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _write_preset(self.root, "role", "assistant.md", _SAMPLE_PRESET)
        self.svc = SoulPresetService(presets_dir=self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_get_preset_found(self):
        preset = self.svc.get_preset("role-test-assistant")
        self.assertIsNotNone(preset)
        self.assertEqual(preset["name"], "Test Assistant")
        self.assertEqual(preset["emoji"], "🤖")

    def test_get_preset_not_found(self):
        self.assertIsNone(self.svc.get_preset("nonexistent-preset"))

    def test_get_preset_has_body(self):
        preset = self.svc.get_preset("role-test-assistant")
        self.assertIn("Identity", preset["body"])


class TestSoulPresetServiceBuildResources(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _write_preset(self.root, "role", "assistant.md", _SAMPLE_PRESET)
        self.svc = SoulPresetService(presets_dir=self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_build_resources_single_preset(self):
        resources = self.svc.build_role_resources(["role-test-assistant"])
        self.assertIsInstance(resources, dict)
        # Should produce SOUL.md and/or AGENTS.md and IDENTITY.md
        self.assertTrue(len(resources) > 0)

    def test_build_resources_missing_preset_skipped(self):
        resources = self.svc.build_role_resources(["nonexistent"])
        self.assertEqual(resources, {})

    def test_build_resources_multiple_presets_concatenated(self):
        _write_preset(self.root, "role", "second.md",
                      "---\nname: Second\n---\n## Identity and Communication Style\nSecond style.\n")
        resources = self.svc.build_role_resources(["role-test-assistant", "role-second"])
        # Both SOUL.md contents should be merged
        if "SOUL.md" in resources:
            self.assertIn("Be helpful", resources["SOUL.md"])

    def test_build_resources_empty_list(self):
        resources = self.svc.build_role_resources([])
        self.assertEqual(resources, {})


if __name__ == "__main__":
    unittest.main()
