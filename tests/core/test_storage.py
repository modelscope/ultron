# Copyright (c) ModelScope Contributors. All rights reserved.
import tempfile
import unittest
from pathlib import Path

from ultron.core.models import Skill, SkillFrontmatter, SkillMeta
from ultron.core.storage import SkillStorage


def _make_storage(tmp: str):
    return SkillStorage(str(Path(tmp) / "skills"), str(Path(tmp) / "archive"))


def _sample_skill(slug="demo", version="1.0.0") -> Skill:
    meta = SkillMeta(owner_id="o", slug=slug, version=version, published_at=0)
    front = SkillFrontmatter(
        name="Demo", description="d",
        metadata={"ultron": {"categories": ["general"], "complexity": "low"}},
    )
    return Skill(meta=meta, frontmatter=front, content="# Body", scripts={"a.sh": "echo 1"})


class TestSkillStorage(unittest.TestCase):
    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            sk = _sample_skill()
            d = st.save_skill(sk)
            loaded = st.load_skill_from_dir(d)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.meta.slug, "demo")
            self.assertEqual(loaded.content.strip(), "# Body")
            self.assertIn("a.sh", loaded.scripts)

    def test_load_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            self.assertIsNone(st.load_skill("nope", "9.9.9"))

    def test_load_skill_from_dir_missing_skill_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            empty_dir = Path(tmp) / "empty"
            empty_dir.mkdir()
            self.assertIsNone(st.load_skill_from_dir(str(empty_dir)))

    def test_load_skill_from_dir_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            self.assertIsNone(st.load_skill_from_dir("/nonexistent/path"))

    def test_skill_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            sk = _sample_skill()
            st.save_skill(sk)
            self.assertTrue(st.skill_exists("demo", "1.0.0"))
            self.assertFalse(st.skill_exists("demo", "9.9.9"))

    def test_get_skill_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            st.save_skill(_sample_skill("s", "1.0.0"))
            st.save_skill(_sample_skill("s", "1.1.0"))
            versions = st.get_skill_versions("s")
            self.assertIn("1.0.0", versions)
            self.assertIn("1.1.0", versions)

    def test_get_latest_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            st.save_skill(_sample_skill("s", "1.0.0"))
            st.save_skill(_sample_skill("s", "1.1.0"))
            latest = st.get_latest_version("s")
            self.assertIsNotNone(latest)

    def test_get_latest_version_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            self.assertIsNone(st.get_latest_version("nonexistent"))

    def test_delete_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            st.save_skill(_sample_skill())
            self.assertTrue(st.delete_skill("demo", "1.0.0"))
            self.assertFalse(st.skill_exists("demo", "1.0.0"))

    def test_delete_skill_missing_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            self.assertFalse(st.delete_skill("nope", "1.0.0"))

    def test_archive_and_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            st.save_skill(_sample_skill())
            arch_path = st.archive_skill("demo", "1.0.0")
            self.assertIsNotNone(arch_path)
            self.assertFalse(st.skill_exists("demo", "1.0.0"))
            restored = st.restore_skill("demo", "1.0.0")
            self.assertIsNotNone(restored)
            self.assertTrue(st.skill_exists("demo", "1.0.0"))

    def test_archive_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            self.assertIsNone(st.archive_skill("nope", "1.0.0"))

    def test_restore_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            self.assertIsNone(st.restore_skill("nope", "1.0.0"))

    def test_copy_skill_to_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            st.save_skill(_sample_skill())
            target = Path(tmp) / "target"
            target.mkdir()
            result = st.copy_skill_to_target("demo", "1.0.0", str(target))
            self.assertIsNotNone(result)
            self.assertTrue(Path(result).exists())

    def test_copy_skill_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            result = st.copy_skill_to_target("nope", "1.0.0", tmp)
            self.assertIsNone(result)

    def test_list_all_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            st.save_skill(_sample_skill("skill-a", "1.0.0"))
            st.save_skill(_sample_skill("skill-b", "2.0.0"))
            skills = st.list_all_skills()
            slugs = [s["slug"] for s in skills]
            self.assertIn("skill-a", slugs)
            self.assertIn("skill-b", slugs)

    def test_get_storage_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            st.save_skill(_sample_skill())
            stats = st.get_storage_stats()
            self.assertEqual(stats["total_skills"], 1)
            self.assertIn("total_size_bytes", stats)

    def test_clear_all_skill_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            st.save_skill(_sample_skill("a", "1.0.0"))
            st.save_skill(_sample_skill("b", "1.0.0"))
            result = st.clear_all_skill_files(include_archive=True)
            self.assertEqual(result["removed_skill_dirs"], 2)
            self.assertEqual(st.list_all_skills(), [])

    def test_read_skill_md_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            st.save_skill(_sample_skill())
            text = st.read_skill_md_text("demo", "1.0.0")
            self.assertIsNotNone(text)
            self.assertIn("Demo", text)

    def test_read_skill_md_text_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            self.assertIsNone(st.read_skill_md_text("nope", "1.0.0"))

    def test_load_skill_without_meta_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = _make_storage(tmp)
            sk = _sample_skill()
            d = st.save_skill(sk)
            # Remove _meta.json to test fallback
            (Path(d) / "_meta.json").unlink()
            loaded = st.load_skill_from_dir(d)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.meta.version, "1.0.0")


if __name__ == "__main__":
    unittest.main()
