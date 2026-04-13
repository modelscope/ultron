# Copyright (c) ModelScope Contributors. All rights reserved.
import tempfile
import unittest
from pathlib import Path

from ultron.core.models import Skill, SkillFrontmatter, SkillMeta, SkillStatus
from ultron.core.storage import SkillStorage


def _sample_skill() -> Skill:
    meta = SkillMeta(
        owner_id="o",
        slug="demo",
        version="1.0.0",
        published_at=0,
        status=SkillStatus.ACTIVE,
    )
    front = SkillFrontmatter(
        name="Demo",
        description="d",
        metadata={"ultron": {"categories": ["general"], "complexity": "low"}},
    )
    return Skill(meta=meta, frontmatter=front, content="# Body", scripts={"a.sh": "echo 1"})


class TestSkillStorage(unittest.TestCase):
    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills = Path(tmp) / "skills"
            arch = Path(tmp) / "archive"
            st = SkillStorage(str(skills), str(arch))
            sk = _sample_skill()
            d = st.save_skill(sk)
            loaded = st.load_skill_from_dir(d)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.meta.slug, "demo")
            self.assertEqual(loaded.content.strip(), "# Body")
            self.assertIn("a.sh", loaded.scripts)

    def test_load_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = SkillStorage(str(Path(tmp) / "s"), str(Path(tmp) / "a"))
            self.assertIsNone(st.load_skill("nope", "9.9.9"))


if __name__ == "__main__":
    unittest.main()
