# Copyright (c) ModelScope Contributors. All rights reserved.
# pylint: disable=protected-access

import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from ultron.core.models import (
    MemoryRecord,
    Skill,
    SkillFrontmatter,
    SkillMeta,
)
from ultron.services.memory import MemorySearchResult
from ultron.services.skill import RetrievalResult


def _memory_record(memory_id: str = "m1") -> MemoryRecord:
    now = datetime.now()
    return MemoryRecord(
        id=memory_id,
        memory_type="pattern",
        content="body",
        context="ctx",
        resolution="res",
        tier="warm",
        hit_count=3,
        status="active",
        created_at=now,
        last_hit_at=now,
        embedding=[],
        tags=["t1"],
    )


def _sample_skill(slug: str = "demo-skill") -> Skill:
    meta = SkillMeta(
        owner_id="owner",
        slug=slug,
        version="1.0.0",
        published_at=0,
    )
    front = SkillFrontmatter(
        name="Demo",
        description="desc",
        metadata={"ultron": {"categories": ["cat-a"], "complexity": "low"}},
    )
    return Skill(meta=meta, frontmatter=front, content="# Skill", scripts={"x.sh": "echo"})


def _mock_ultron_for_lifespan():
    """
    Build a MagicMock whose config keeps lifespan cheap (no async embedding queue).
    """
    m = MagicMock()
    m.config.async_embedding = False
    m.config.decay_interval_hours = 24.0
    m.db = MagicMock()
    return m


class TestUltronServerRoutes(unittest.TestCase):
    """
    HTTP-level FastAPI route contracts for ultron.server.

    Patches ultron.server_state.ultron so tests avoid real storage and LLM calls.
    """

    def setUp(self):
        import ultron.server as srv
        import ultron.server_state as st

        self._srv = srv
        self.mock_ultron = _mock_ultron_for_lifespan()
        self.patcher = patch.object(st, "ultron", self.mock_ultron)
        self.patcher.start()
        self.client = TestClient(srv.app)

    def tearDown(self):
        self.client.close()
        self.patcher.stop()

    def test_root_redirects_to_dashboard(self):
        r = self.client.get("/", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers.get("location"), "/dashboard")

    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("service"), "ultron")
        self.assertIn("version", data)

    def test_get_stats_delegates(self):
        self.mock_ultron.get_stats.return_value = {"memory": {"total": 1}}
        r = self.client.get("/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["memory"]["total"], 1)
        self.mock_ultron.get_stats.assert_called_once()

    def test_upload_memory(self):
        rec = _memory_record("mid-1")
        self.mock_ultron.upload_memory.return_value = rec
        r = self.client.post(
            "/memory/upload",
            json={
                "content": "c",
                "context": "",
                "resolution": "",
                "tags": [],
            },
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("success"))
        self.assertEqual(body["data"]["id"], "mid-1")
        self.assertEqual(body["data"]["memory_type"], "pattern")

    def test_upload_memory_minimal(self):
        rec = _memory_record("mid-1")
        self.mock_ultron.upload_memory.return_value = rec
        r = self.client.post(
            "/memory/upload",
            json={"content": "c", "context": "", "resolution": "", "tags": []},
        )
        self.assertEqual(r.status_code, 200)
        self.mock_ultron.upload_memory.assert_called_once()

    def test_search_memory(self):
        rec = _memory_record()
        msr = MemorySearchResult(
            record=rec, similarity_score=0.91, tier_boosted_score=0.95,
        )
        self.mock_ultron.search_memories.return_value = [msr]
        r = self.client.post(
            "/memory/search",
            json={"query": "q", "limit": 5, "detail_level": "l0"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("success"))
        self.assertEqual(body["count"], 1)
        self.assertNotIn("embedding", body["data"][0])

    def test_search_memory_rejects_full_detail_level(self):
        r = self.client.post(
            "/memory/search",
            json={"query": "q", "detail_level": "full"},
        )
        self.assertEqual(r.status_code, 422)

    def test_memory_details(self):
        rec = _memory_record("id-a")
        self.mock_ultron.get_memory_details.return_value = [rec]
        r = self.client.post("/memory/details", json={"memory_ids": ["id-a"]})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["data"][0]["id"], "id-a")
        self.assertNotIn("embedding", body["data"][0])

    def test_memory_stats(self):
        self.mock_ultron.get_memory_stats.return_value = {"by_tier": {}}
        r = self.client.get("/memory/stats")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("success"))

    def test_ingest_success_shape(self):
        self.mock_ultron.ingest.return_value = {"successful": 1, "results": []}
        r = self.client.post("/ingest", json={"paths": ["/tmp/x"], "agent_id": "test-agent"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("success"))

    def test_ingest_no_success_flag(self):
        self.mock_ultron.ingest.return_value = {"successful": 0, "results": []}
        r = self.client.post("/ingest", json={"paths": ["/tmp/x"], "agent_id": "test-agent"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json().get("success"))

    def test_ingest_text(self):
        self.mock_ultron.ingest_text.return_value = {"success": True, "items": []}
        r = self.client.post("/ingest/text", json={"text": "hello"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("success"))

    def test_skills_search(self):
        skill = _sample_skill()
        rr = RetrievalResult(
            skill=skill,
            similarity_score=0.88,
            combined_score=0.85,
        )
        self.mock_ultron.search_skills.return_value = [rr]
        r = self.client.post("/skills/search", json={"query": "q", "limit": 3})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["count"], 1)
        row = data["data"][0]
        self.assertEqual(row["slug"], "demo-skill")
        self.assertEqual(row["categories"], ["cat-a"])

    def test_list_skills(self):
        self.mock_ultron.list_all_skills.return_value = [{"slug": "a"}]
        r = self.client.get("/skills")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 1)

    def test_skills_upload(self):
        self.mock_ultron.upload_skills.return_value = {
            "total": 1,
            "successful": 1,
            "results": [],
        }
        r = self.client.post(
            "/skills/upload",
            json={"paths": ["/skills/x"]},
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("success"))

    def test_skills_install_success(self):
        self.mock_ultron.install_skill_to.return_value = {
            "success": True, "full_name": "@org/skill", "source": "internal",
            "installed_path": "/tmp/skill",
        }
        r = self.client.post(
            "/skills/install",
            json={"full_name": "@org/skill", "target_dir": "/tmp"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("success"))

    def test_skills_install_failure(self):
        self.mock_ultron.install_skill_to.return_value = {
            "success": False, "error": "modelscope CLI not found",
        }
        r = self.client.post(
            "/skills/install",
            json={"full_name": "@org/skill", "target_dir": "/tmp"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json().get("success"))

    def test_dashboard_overview(self):
        self.mock_ultron.get_memory_stats.return_value = {"by_tier": {"hot": 5}}
        self.mock_ultron.db._get_connection.return_value.__enter__ = MagicMock(
            return_value=MagicMock()
        )
        self.mock_ultron.db._get_connection.return_value.__exit__ = MagicMock(
            return_value=False
        )
        # Use a real DB for this test to avoid complex mock setup
        import tempfile, os
        from ultron.core.database import Database
        with tempfile.TemporaryDirectory() as tmp:
            real_db = Database(os.path.join(tmp, "test.db"))
            self.mock_ultron.db = real_db
            r = self.client.get("/dashboard/overview")
            self.assertEqual(r.status_code, 200)
            data = r.json()
            self.assertIn("memory", data)
            self.assertIn("skills", data)

    def test_dashboard_memories(self):
        self.mock_ultron.db.search_memories_by_text.return_value = ([], 0)
        r = self.client.get("/dashboard/memories")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("data", data)
        self.assertEqual(data["total"], 0)

    def test_dashboard_skills(self):
        self.mock_ultron.db.search_skills_by_text.return_value = ([], 0)
        r = self.client.get("/dashboard/skills")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("data", data)
        self.assertEqual(data["total"], 0)

    def test_dashboard_leaderboard(self):
        self.mock_ultron.db.get_memory_leaderboard.return_value = []
        r = self.client.get("/dashboard/leaderboard")
        self.assertEqual(r.status_code, 200)

    def test_dashboard_internal_skill_md_found(self):
        self.mock_ultron.get_internal_skill_md_text.return_value = "# Skill content"
        r = self.client.get("/dashboard/skills/internal/my-skill/skill-md")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["content"], "# Skill content")

    def test_dashboard_internal_skill_md_not_found(self):
        self.mock_ultron.get_internal_skill_md_text.return_value = None
        r = self.client.get("/dashboard/skills/internal/missing-skill/skill-md")
        self.assertEqual(r.status_code, 404)

    def test_upload_memory_missing_content_rejected(self):
        r = self.client.post("/memory/upload", json={"context": "c", "resolution": "r", "tags": []})
        self.assertEqual(r.status_code, 422)

    def test_search_memory_empty_query(self):
        self.mock_ultron.search_memories.return_value = []
        r = self.client.post("/memory/search", json={"query": "", "limit": 5})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 0)

    def test_memory_details_empty_ids(self):
        self.mock_ultron.get_memory_details.return_value = []
        r = self.client.post("/memory/details", json={"memory_ids": []})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 0)


if __name__ == "__main__":
    unittest.main()
