# Copyright (c) ModelScope Contributors. All rights reserved.
import unittest

from ultron.services.harness.merge import (
    FullMergeResult,
    HeartbeatMerger,
    MergeAction,
    MergeResult,
    SectionMerger,
    _extract_user_diff_text,
    _resolve_target_path,
    merge_resources,
)


class TestSectionMergerParse(unittest.TestCase):
    def setUp(self):
        self.merger = SectionMerger()

    def test_parse_no_headings(self):
        sections = self.merger.parse_sections("just some text\nmore text")
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].title, "")

    def test_parse_with_headings(self):
        content = "preamble\n## Section A\nbody A\n## Section B\nbody B"
        sections = self.merger.parse_sections(content)
        titles = [s.title for s in sections]
        self.assertIn("## Section A", titles)
        self.assertIn("## Section B", titles)

    def test_sections_to_content_roundtrip(self):
        content = "preamble\n## Section A\nbody A\n## Section B\nbody B"
        sections = self.merger.parse_sections(content)
        restored = self.merger.sections_to_content(sections)
        self.assertIn("## Section A", restored)
        self.assertIn("body A", restored)

    def test_parse_empty_string(self):
        sections = self.merger.parse_sections("")
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].title, "")


class TestSectionMergerDiff(unittest.TestCase):
    def setUp(self):
        self.merger = SectionMerger()

    def test_unchanged_section(self):
        content = "## Section A\nbody A"
        default = "## Section A\nbody A"
        unchanged, modified, added = self.merger.diff_sections(content, default)
        # parse_sections always includes a preamble section (empty title) + the heading section
        self.assertEqual(len(modified), 0)
        self.assertEqual(len(added), 0)
        titled_unchanged = [s for s in unchanged if s.title]
        self.assertEqual(len(titled_unchanged), 1)

    def test_modified_section(self):
        content = "## Section A\nmodified body"
        default = "## Section A\noriginal body"
        unchanged, modified, added = self.merger.diff_sections(content, default)
        self.assertEqual(len(modified), 1)
        self.assertEqual(modified[0].title, "## Section A")

    def test_added_section(self):
        content = "## Section A\nbody A\n## New Section\nnew body"
        default = "## Section A\nbody A"
        unchanged, modified, added = self.merger.diff_sections(content, default)
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0].title, "## New Section")

    def test_modified_preamble(self):
        content = "custom preamble\n## Section A\nbody"
        default = "default preamble\n## Section A\nbody"
        unchanged, modified, added = self.merger.diff_sections(content, default)
        preamble_modified = any(s.title == "" for s in modified)
        self.assertTrue(preamble_modified)


class TestSectionMergerMerge(unittest.TestCase):
    def setUp(self):
        self.merger = SectionMerger()

    def test_merge_same_product_keeps_user_modifications(self):
        user = "## Section A\nuser modified\n## Section B\ndefault B"
        source_default = "## Section A\noriginal A\n## Section B\ndefault B"
        target_default = "## Section A\noriginal A\n## Section B\ndefault B"
        result = self.merger.merge(user, source_default, target_default)
        self.assertIn("user modified", result.content)

    def test_merge_appends_user_added_sections(self):
        user = "## Section A\nbody A\n## Custom Section\ncustom content"
        source_default = "## Section A\nbody A"
        target_default = "## Section A\nbody A"
        result = self.merger.merge(user, source_default, target_default)
        self.assertIn("## Custom Section", result.content)
        self.assertIn("custom content", result.content)

    def test_merge_uses_target_default_for_unchanged(self):
        user = "## Section A\noriginal A"
        source_default = "## Section A\noriginal A"
        target_default = "## Section A\ntarget version A"
        result = self.merger.merge(user, source_default, target_default)
        self.assertIn("target version A", result.content)

    def test_merge_returns_actions(self):
        user = "## Section A\nmodified"
        source_default = "## Section A\noriginal"
        target_default = "## Section A\noriginal"
        result = self.merger.merge(user, source_default, target_default)
        self.assertIsInstance(result, MergeResult)
        self.assertGreater(len(result.actions), 0)


class TestHeartbeatMerger(unittest.TestCase):
    def setUp(self):
        self.merger = HeartbeatMerger()

    def test_merge_adds_new_tasks(self):
        user = "## Active Tasks\n- [ ] New task from user\n- [ ] Default task"
        source_default = "## Active Tasks\n- [ ] Default task"
        target_default = "## Active Tasks\n- [ ] Default task"
        result = self.merger.merge(user, source_default, target_default)
        self.assertIn("New task from user", result.content)

    def test_merge_no_new_tasks(self):
        user = "## Active Tasks\n- [ ] Default task"
        source_default = "## Active Tasks\n- [ ] Default task"
        target_default = "## Active Tasks\n- [ ] Default task"
        result = self.merger.merge(user, source_default, target_default)
        # No task_merged action when no new tasks
        task_actions = [a for a in result.actions if a.action == "task_merged"]
        self.assertEqual(len(task_actions), 0)

    def test_extract_task_lines_skips_comments(self):
        body = "- [ ] Task 1\n<!-- comment -->\n- [ ] Task 2"
        lines = self.merger._extract_task_lines(body)
        self.assertEqual(len(lines), 2)
        self.assertNotIn("<!-- comment -->", lines)


class TestExtractUserDiffText(unittest.TestCase):
    def test_extracts_user_additions(self):
        user = "default line\nuser added line"
        default = "default line"
        diff = _extract_user_diff_text(user, default)
        self.assertIn("user added line", diff)
        self.assertNotIn("default line", diff)

    def test_no_changes_returns_empty(self):
        content = "same content"
        default = "same content"
        diff = _extract_user_diff_text(content, default)
        self.assertEqual(diff, "")

    def test_no_default_returns_all_content(self):
        content = "all user content"
        diff = _extract_user_diff_text(content, "")
        self.assertEqual(diff, "all user content")


class TestResolveTargetPath(unittest.TestCase):
    def test_same_product_returns_same_path(self):
        self.assertEqual(_resolve_target_path("nanobot", "SOUL.md", "nanobot"), "SOUL.md")

    def test_cross_product_soul_md(self):
        self.assertEqual(_resolve_target_path("nanobot", "SOUL.md", "openclaw"), "SOUL.md")
        self.assertEqual(_resolve_target_path("nanobot", "SOUL.md", "hermes"), "SOUL.md")

    def test_cross_product_user_md(self):
        self.assertEqual(_resolve_target_path("nanobot", "USER.md", "hermes"), "memories/USER.md")

    def test_cross_product_memory_md(self):
        # nanobot memory/MEMORY.md -> openclaw MEMORY.md
        self.assertEqual(_resolve_target_path("nanobot", "memory/MEMORY.md", "openclaw"), "MEMORY.md")

    def test_cross_product_no_mapping_passthrough(self):
        # skills/ files have no explicit mapping — passthrough
        result = _resolve_target_path("nanobot", "skills/my-skill/SKILL.md", "openclaw")
        self.assertEqual(result, "skills/my-skill/SKILL.md")

    def test_cross_product_none_mapping(self):
        # nanobot memory/HISTORY.md has no hermes equivalent
        result = _resolve_target_path("nanobot", "memory/HISTORY.md", "hermes")
        self.assertIsNone(result)

    def test_qwenpaw_soul_md(self):
        self.assertEqual(_resolve_target_path("qwenpaw", "SOUL.md", "openhuman"), "SOUL.md")
        self.assertEqual(_resolve_target_path("nanobot", "SOUL.md", "qwenpaw"), "SOUL.md")

    def test_openhuman_user_md(self):
        # openhuman USER.md <-> nanobot/openclaw USER.md, hermes memories/USER.md
        self.assertEqual(_resolve_target_path("openhuman", "USER.md", "nanobot"), "USER.md")
        self.assertEqual(_resolve_target_path("openhuman", "USER.md", "hermes"), "memories/USER.md")

    def test_identity_openclaw_openhuman(self):
        self.assertEqual(_resolve_target_path("openclaw", "IDENTITY.md", "openhuman"), "IDENTITY.md")
        # qwenpaw has no IDENTITY concept
        self.assertIsNone(_resolve_target_path("openclaw", "IDENTITY.md", "qwenpaw"))

    def test_profile_qwenpaw_openhuman(self):
        self.assertEqual(_resolve_target_path("qwenpaw", "PROFILE.md", "openhuman"), "PROFILE.md")
        # nanobot has no PROFILE concept
        self.assertIsNone(_resolve_target_path("qwenpaw", "PROFILE.md", "nanobot"))

    def test_memory_cross_new_products(self):
        self.assertEqual(_resolve_target_path("openhuman", "MEMORY.md", "qwenpaw"), "MEMORY.md")
        self.assertEqual(_resolve_target_path("qwenpaw", "MEMORY.md", "nanobot"), "memory/MEMORY.md")


class TestMergeResources(unittest.TestCase):
    def test_same_product_imports_directly(self):
        incoming = {"SOUL.md": "my soul", "USER.md": "my user"}
        result = merge_resources(
            incoming=incoming,
            source_product="nanobot",
            target_product="nanobot",
            source_defaults={},
            target_defaults={},
        )
        self.assertIn("SOUL.md", result.merged_files)
        self.assertEqual(result.merged_files["SOUL.md"], "my soul")

    def test_fills_missing_from_target_defaults(self):
        result = merge_resources(
            incoming={},
            source_product="nanobot",
            target_product="nanobot",
            source_defaults={},
            target_defaults={"SOUL.md": "default soul"},
        )
        self.assertIn("SOUL.md", result.merged_files)
        self.assertEqual(result.merged_files["SOUL.md"], "default soul")

    def test_skill_import(self):
        incoming = {"skills/my-skill/SKILL.md": "# Skill content"}
        result = merge_resources(
            incoming=incoming,
            source_product="nanobot",
            target_product="nanobot",
            source_defaults={},
            target_defaults={},
        )
        self.assertIn("skills/my-skill/SKILL.md", result.merged_files)

    def test_skill_skip_if_exists(self):
        incoming = {"skills/existing-skill/SKILL.md": "# Skill"}
        result = merge_resources(
            incoming=incoming,
            source_product="nanobot",
            target_product="nanobot",
            source_defaults={},
            target_defaults={},
            existing_skills=["existing-skill"],
        )
        self.assertNotIn("skills/existing-skill/SKILL.md", result.merged_files)
        skip_actions = [a for a in result.actions if a.action == "skip"]
        self.assertEqual(len(skip_actions), 1)

    def test_cross_product_soul_md_merged(self):
        incoming = {"SOUL.md": "## Identity\nuser identity\n## Rules\ndefault rules"}
        source_defaults = {"SOUL.md": "## Identity\ndefault identity\n## Rules\ndefault rules"}
        target_defaults = {"SOUL.md": "## Identity\ndefault identity\n## Rules\ndefault rules"}
        result = merge_resources(
            incoming=incoming,
            source_product="nanobot",
            target_product="openclaw",
            source_defaults=source_defaults,
            target_defaults=target_defaults,
        )
        self.assertIn("SOUL.md", result.merged_files)
        self.assertIn("user identity", result.merged_files["SOUL.md"])

    def test_mutually_exclusive_content_into_catch_all(self):
        # openclaw BOOTSTRAP.md has no hermes equivalent -> user diff lands in
        # hermes catch-all (SOUL.md, since hermes has no AGENTS.md).
        incoming = {
            "SOUL.md": "## Core\nmy soul",
            "BOOTSTRAP.md": "default line\nMY CUSTOM STEP",
        }
        source_defaults = {
            "SOUL.md": "## Core\ndefault soul",
            "BOOTSTRAP.md": "default line",
        }
        target_defaults = {"SOUL.md": "## Core\ndefault soul"}
        result = merge_resources(
            incoming=incoming,
            source_product="openclaw",
            target_product="hermes",
            source_defaults=source_defaults,
            target_defaults=target_defaults,
        )
        self.assertNotIn("BOOTSTRAP.md", result.merged_files)
        self.assertIn("MY CUSTOM STEP", result.merged_files["SOUL.md"])
        self.assertIn("## Imported from openclaw BOOTSTRAP.md", result.merged_files["SOUL.md"])

    def test_mutually_exclusive_uses_agents_md_when_available(self):
        # nanobot memory/HISTORY.md is data (memory/) -> kept as-is, not overflow.
        # A non-data product-only file overflows into AGENTS.md for qwenpaw.
        incoming = {"TOOLS.md": "default tools\nMY TOOL NOTE"}
        source_defaults = {"TOOLS.md": "default tools"}
        target_defaults = {"AGENTS.md": "## Red Lines\nx", "SOUL.md": "y"}
        result = merge_resources(
            incoming=incoming,
            source_product="nanobot",
            target_product="qwenpaw",  # no TOOLS, has AGENTS.md
            source_defaults=source_defaults,
            target_defaults=target_defaults,
        )
        self.assertIn("MY TOOL NOTE", result.merged_files["AGENTS.md"])
        self.assertNotIn("TOOLS.md", result.merged_files)

    def test_mutually_exclusive_no_user_changes_skipped(self):
        # File equals its source default -> no diff -> skipped, not written.
        incoming = {"BOOTSTRAP.md": "default line"}
        source_defaults = {"BOOTSTRAP.md": "default line"}
        target_defaults = {"SOUL.md": "soul"}
        result = merge_resources(
            incoming=incoming,
            source_product="openclaw",
            target_product="hermes",
            source_defaults=source_defaults,
            target_defaults=target_defaults,
        )
        self.assertNotIn("BOOTSTRAP.md", result.merged_files)
        self.assertNotIn("Imported from", result.merged_files.get("SOUL.md", ""))
        skip_actions = [a for a in result.actions if a.action == "skip"]
        self.assertTrue(skip_actions)

    def test_data_files_kept_as_is(self):
        # memory/ and wiki/ files have no cross-product mapping but are data,
        # so they are imported as-is rather than flattened into a persona file.
        incoming = {"memory/HISTORY.md": "raw log\nNEW EVENT"}
        result = merge_resources(
            incoming=incoming,
            source_product="nanobot",
            target_product="hermes",
            source_defaults={"memory/HISTORY.md": "raw log"},
            target_defaults={"SOUL.md": "soul"},
        )
        self.assertIn("memory/HISTORY.md", result.merged_files)
        self.assertNotIn("Imported from", result.merged_files.get("SOUL.md", ""))

    def test_cross_product_new_product_migration(self):
        # qwenpaw -> openhuman: SOUL merges, PROFILE maps directly.
        incoming = {
            "SOUL.md": "## Core Truths\nmy custom soul\n",
            "PROFILE.md": "default profile\nMY NAME IS ZED\n",
        }
        source_defaults = {
            "SOUL.md": "## Core Truths\ndefault soul\n",
            "PROFILE.md": "default profile\n",
        }
        target_defaults = {
            "SOUL.md": "## Core Truths\ndefault soul\n",
            "PROFILE.md": "default profile\n",
        }
        result = merge_resources(
            incoming=incoming,
            source_product="qwenpaw",
            target_product="openhuman",
            source_defaults=source_defaults,
            target_defaults=target_defaults,
        )
        self.assertIn("my custom soul", result.merged_files["SOUL.md"])
        self.assertIn("MY NAME IS ZED", result.merged_files["PROFILE.md"])

    def test_returns_full_merge_result(self):
        result = merge_resources(
            incoming={},
            source_product="nanobot",
            target_product="nanobot",
            source_defaults={},
            target_defaults={},
        )
        self.assertIsInstance(result, FullMergeResult)
        self.assertIsInstance(result.merged_files, dict)
        self.assertIsInstance(result.actions, list)


if __name__ == "__main__":
    unittest.main()
