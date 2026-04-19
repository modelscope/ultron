# Copyright (c) ModelScope Contributors. All rights reserved.
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from ultron.api.sdk import Ultron


class TestUltronHelpers(unittest.TestCase):
    """Ultron SDK helpers that do not require a full instance initialisation."""

    def test_increment_version(self):
        u = object.__new__(Ultron)
        self.assertEqual(u._increment_version("2.1.3"), "2.1.4")

    def test_increment_version_fallback(self):
        u = object.__new__(Ultron)
        self.assertEqual(u._increment_version("not-a-version"), "1.0.1")

    def test_increment_version_major_minor(self):
        u = object.__new__(Ultron)
        self.assertEqual(u._increment_version("1.0.0"), "1.0.1")
        self.assertEqual(u._increment_version("3.5.9"), "3.5.10")


class TestUltronCoreArchive(unittest.TestCase):
    """CoreMixin._archive_skill_tree with archive disabled."""

    def _make_ultron(self, archive=False):
        u = object.__new__(Ultron)
        u.config = MagicMock()
        u.config.archive_raw_uploads = archive
        u.db = MagicMock()
        return u

    def test_archive_disabled_no_db_call(self):
        u = self._make_ultron(archive=False)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "SKILL.md").write_text("# skill")
            u._archive_skill_tree(tmp)
            u.db.save_raw_user_upload.assert_not_called()

    def test_archive_enabled_saves_files(self):
        u = self._make_ultron(archive=True)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "SKILL.md").write_text("# skill")
            (Path(tmp) / "script.sh").write_text("echo hi")
            u._archive_skill_tree(tmp)
            self.assertGreater(u.db.save_raw_user_upload.call_count, 0)

    def test_archive_skips_hidden_files(self):
        u = self._make_ultron(archive=True)
        with tempfile.TemporaryDirectory() as tmp:
            hidden = Path(tmp) / ".hidden"
            hidden.mkdir()
            (hidden / "secret.txt").write_text("secret")
            (Path(tmp) / "SKILL.md").write_text("# skill")
            u._archive_skill_tree(tmp)
            # Only SKILL.md should be archived, not .hidden/secret.txt
            for call in u.db.save_raw_user_upload.call_args_list:
                rel = call[1].get("meta", {}).get("rel_path", "")
                self.assertNotIn(".hidden", rel)

    def test_archive_nonexistent_dir_no_crash(self):
        u = self._make_ultron(archive=True)
        u._archive_skill_tree("/nonexistent/path")
        u.db.save_raw_user_upload.assert_not_called()


class TestUltronCoreStats(unittest.TestCase):
    def _make_ultron(self):
        u = object.__new__(Ultron)
        u.storage = MagicMock()
        u.catalog = MagicMock()
        u.embedding = MagicMock()
        u.memory_service = MagicMock()
        u.storage.get_storage_stats.return_value = {"total_skills": 5}
        u.catalog.get_category_statistics.return_value = {"total_skills": 5}
        u.embedding.get_model_info.return_value = {"model": "text-embedding-v4"}
        u.memory_service.get_memory_stats.return_value = {"total": 100}
        return u

    def test_get_stats_shape(self):
        u = self._make_ultron()
        stats = u.get_stats()
        self.assertIn("storage", stats)
        self.assertIn("categories", stats)
        self.assertIn("embedding", stats)
        self.assertIn("memory", stats)

    def test_list_all_skills_delegates(self):
        u = self._make_ultron()
        u.storage.list_all_skills.return_value = [{"slug": "a"}]
        result = u.list_all_skills()
        self.assertEqual(len(result), 1)
        u.storage.list_all_skills.assert_called_once()


class TestUltronMemoryMixin(unittest.TestCase):
    def _make_ultron(self):
        u = object.__new__(Ultron)
        u.memory_service = MagicMock()
        u.smart_ingestion = MagicMock()
        return u

    def test_upload_memory_delegates(self):
        u = self._make_ultron()
        u.memory_service.upload_memory.return_value = MagicMock()
        u.upload_memory("content", "ctx", "res", tags=["t1"])
        u.memory_service.upload_memory.assert_called_once_with(
            content="content", context="ctx", resolution="res", tags=["t1"]
        )

    def test_search_memories_delegates(self):
        u = self._make_ultron()
        u.memory_service.search_memories.return_value = []
        result = u.search_memories("query", limit=5)
        self.assertEqual(result, [])
        u.memory_service.search_memories.assert_called_once()

    def test_get_memory_details_delegates(self):
        u = self._make_ultron()
        u.memory_service.get_memory_details.return_value = []
        u.get_memory_details(["id1", "id2"])
        u.memory_service.get_memory_details.assert_called_once_with(["id1", "id2"])

    def test_run_tier_rebalance_delegates(self):
        u = self._make_ultron()
        u.memory_service.run_tier_rebalance.return_value = {"hot": 5}
        result = u.run_tier_rebalance()
        self.assertEqual(result["hot"], 5)

    def test_run_memory_decay_is_alias(self):
        u = self._make_ultron()
        u.memory_service.run_tier_rebalance.return_value = {"ok": True}
        result = u.run_memory_decay()
        self.assertTrue(result["ok"])

    def test_ingest_delegates(self):
        u = self._make_ultron()
        u.smart_ingestion.ingest.return_value = {"total_files": 1}
        u.ingest(["/tmp/x"], agent_id="agent1")
        u.smart_ingestion.ingest.assert_called_once_with(paths=["/tmp/x"], agent_id="agent1")

    def test_ingest_text_delegates(self):
        u = self._make_ultron()
        u.smart_ingestion.ingest_text.return_value = {"success": True}
        result = u.ingest_text("hello world")
        self.assertTrue(result["success"])


class TestUltronSkillMixin(unittest.TestCase):
    def _make_ultron(self):
        u = object.__new__(Ultron)
        u.storage = MagicMock()
        u.db = MagicMock()
        u.embedding = MagicMock()
        u.catalog = MagicMock()
        u.config = MagicMock()
        u.config.archive_raw_uploads = False
        u.retriever = MagicMock()
        return u

    def test_search_skills_delegates(self):
        u = self._make_ultron()
        u.retriever.search_skills.return_value = []
        result = u.search_skills("query", limit=3)
        self.assertEqual(result, [])
        u.retriever.search_skills.assert_called_once()

    def test_get_skill_no_version(self):
        u = self._make_ultron()
        u.storage.get_latest_version.return_value = None
        result = u.get_skill("nonexistent")
        self.assertIsNone(result)

    def test_get_skill_with_version(self):
        u = self._make_ultron()
        u.storage.get_latest_version.return_value = None
        mock_skill = MagicMock()
        u.storage.load_skill.return_value = mock_skill
        result = u.get_skill("my-skill", version="1.0.0")
        self.assertEqual(result, mock_skill)

    def test_upload_skills_path_not_found(self):
        u = self._make_ultron()
        result = u.upload_skills(["/nonexistent/path"])
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["successful"], 0)
        self.assertIn("not found", result["results"][0]["error"])

    def test_upload_skills_no_skill_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            u = self._make_ultron()
            result = u.upload_skills([tmp])
            self.assertEqual(result["total"], 0)

    def test_install_skill_modelscope_not_found(self):
        u = self._make_ultron()
        u.storage.get_latest_version.return_value = None
        result = u.install_skill_to("@org/skill", "/tmp/target")
        self.assertFalse(result["success"])
        self.assertIn("modelscope", result["error"].lower())

    def test_get_internal_skill_md_not_in_db(self):
        u = self._make_ultron()
        u.db.get_skill.return_value = None
        result = u.get_internal_skill_md_text("missing")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
