# Copyright (c) ModelScope Contributors. All rights reserved.
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ultron.config import UltronConfig, _skip_dotenv, load_ultron_dotenv


class TestUltronConfig(unittest.TestCase):
    """UltronConfig paths and clamped env-backed fields."""

    def test_db_path_skills_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = UltronConfig(data_dir=tmp, db_name="x.db")
            self.assertEqual(cfg.db_path, Path(tmp) / "x.db")
            self.assertEqual(cfg.skills_dir, Path(tmp) / "skills")
            self.assertEqual(cfg.archive_dir, Path(tmp) / "archive")

    def test_ensure_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            sub = Path(tmp) / "nest"
            cfg = UltronConfig(data_dir=str(sub))
            cfg.ensure_directories()
            self.assertTrue(sub.is_dir())
            self.assertTrue((sub / "skills").is_dir())

    def test_hot_percentile_clamped(self):
        with patch.dict(os.environ, {"ULTRON_HOT_PERCENTILE": "200"}, clear=False):
            c = UltronConfig()
            self.assertEqual(c.hot_percentile, 100)


class TestDotenvHelpers(unittest.TestCase):
    """Optional dotenv merge (no network)."""

    def test_skip_dotenv_flags(self):
        with patch.dict(os.environ, {"ULTRON_SKIP_DOTENV": "1"}, clear=False):
            self.assertTrue(_skip_dotenv())
        with patch.dict(os.environ, {"ULTRON_SKIP_DOTENV": ""}, clear=False):
            self.assertFalse(_skip_dotenv())

    def test_load_ultron_dotenv_skipped_no_crash(self):
        with patch.dict(os.environ, {"ULTRON_SKIP_DOTENV": "true"}, clear=False):
            load_ultron_dotenv()


if __name__ == "__main__":
    unittest.main()
