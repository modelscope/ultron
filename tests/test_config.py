# Copyright (c) ModelScope Contributors. All rights reserved.
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ultron.config import UltronConfig, load_ultron_dotenv


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

    def test_models_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = UltronConfig(data_dir=tmp)
            self.assertEqual(cfg.models_dir, Path(tmp) / "models")

    def test_ensure_directories_creates_models_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            sub = Path(tmp) / "d"
            cfg = UltronConfig(data_dir=str(sub))
            cfg.ensure_directories()
            self.assertTrue((sub / "models").is_dir())

    def test_warm_percentile_clamped_low(self):
        with patch.dict(os.environ, {"ULTRON_WARM_PERCENTILE": "0"}, clear=False):
            c = UltronConfig()
            self.assertGreaterEqual(c.warm_percentile, 1)

    def test_dedup_threshold_defaults(self):
        cfg = UltronConfig()
        self.assertGreater(cfg.dedup_similarity_threshold, 0)
        self.assertLessEqual(cfg.dedup_similarity_threshold, 1.0)
        self.assertGreater(cfg.dedup_soft_threshold, 0)

    def test_crystallization_threshold_min(self):
        with patch.dict(os.environ, {"ULTRON_CRYSTALLIZATION_THRESHOLD": "0"}, clear=False):
            c = UltronConfig()
            self.assertGreaterEqual(c.crystallization_threshold, 2)

    def test_evolution_batch_limit_min(self):
        with patch.dict(os.environ, {"ULTRON_EVOLUTION_BATCH_LIMIT": "0"}, clear=False):
            c = UltronConfig()
            self.assertGreaterEqual(c.evolution_batch_limit, 1)

    def test_llm_max_retries_min(self):
        with patch.dict(os.environ, {"ULTRON_LLM_MAX_RETRIES": "-5"}, clear=False):
            c = UltronConfig()
            self.assertGreaterEqual(c.llm_max_retries, 0)

    def test_resolve_jwt_secret_from_env(self):
        with patch.dict(os.environ, {"ULTRON_JWT_SECRET": "mysecret"}, clear=False):
            with tempfile.TemporaryDirectory() as tmp:
                cfg = UltronConfig(data_dir=tmp)
                secret = cfg.resolve_jwt_secret()
                self.assertEqual(secret, "mysecret")

    def test_resolve_jwt_secret_generates_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {}, clear=False):
                # Remove JWT secret from env if present
                env = {k: v for k, v in os.environ.items() if k != "ULTRON_JWT_SECRET"}
                with patch.dict(os.environ, env, clear=True):
                    cfg = UltronConfig(data_dir=tmp)
                    secret1 = cfg.resolve_jwt_secret()
                    self.assertTrue(len(secret1) > 0)
                    # Second call returns same secret
                    secret2 = cfg.resolve_jwt_secret()
                    self.assertEqual(secret1, secret2)
                    # File was persisted
                    self.assertTrue((Path(tmp) / ".jwt_secret").exists())

    def test_resolve_jwt_secret_reads_persisted_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            secret_file = Path(tmp) / ".jwt_secret"
            secret_file.write_text("persisted-secret")
            with patch.dict(os.environ, {}, clear=True):
                cfg = UltronConfig(data_dir=tmp)
                secret = cfg.resolve_jwt_secret()
                self.assertEqual(secret, "persisted-secret")

    def test_env_bool_false_values(self):
        for val in ("0", "false", "no", "off"):
            with patch.dict(os.environ, {"ULTRON_EVOLUTION_ENABLED": val}, clear=False):
                c = UltronConfig()
                self.assertFalse(c.evolution_enabled)

    def test_env_bool_true_default(self):
        with patch.dict(os.environ, {"ULTRON_EVOLUTION_ENABLED": "1"}, clear=False):
            c = UltronConfig()
            self.assertTrue(c.evolution_enabled)


class TestDotenvHelpers(unittest.TestCase):
    """load_ultron_dotenv is safe without ~/.ultron/.env."""

    def test_load_ultron_dotenv_no_crash(self):
        load_ultron_dotenv()


if __name__ == "__main__":
    unittest.main()

