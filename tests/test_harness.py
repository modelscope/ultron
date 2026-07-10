# Copyright (c) ModelScope Contributors. All rights reserved.
import json
import os
import tempfile
import unittest
from pathlib import Path

from ultron.core.database import Database
from ultron.services.harness import HarnessService
from ultron.services.harness.allowlist import (
    ALLOWLIST_REGISTRY,
    ClawWorkspaceAllowlist,
    NanobotWorkspaceAllowlist,
)
from ultron.services.harness.bundle import HarnessBundle


class TestHarnessMixin(unittest.TestCase):
    """Database-level CRUD for agents, profiles, and shares."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self.tmp.name, "test.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_register_and_list_agents(self):
        self.db.register_agent("u1", "d1", "Laptop")
        self.db.register_agent("u1", "d2", "Desktop")
        agents = self.db.list_agents("u1")
        self.assertEqual(len(agents), 2)
        self.assertEqual(agents[0]["display_name"], "Laptop")

    def test_register_agent_idempotent(self):
        self.db.register_agent("u1", "d1", "Laptop")
        self.db.register_agent("u1", "d1", "Laptop v2")
        agents = self.db.list_agents("u1")
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]["display_name"], "Laptop v2")

    def test_delete_agent_cascades(self):
        self.db.register_agent("u1", "d1")
        self.db.upsert_profile("u1", "d1", '{"a":"b"}', "nanobot")
        self.db.create_share("tok1", "u1", "d1", "link", '{}', "abc123")
        self.db.delete_agent("u1", "d1")
        self.assertIsNone(self.db.get_profile("u1", "d1"))
        self.assertIsNone(self.db.get_share("tok1"))
        self.assertEqual(len(self.db.list_agents("u1")), 0)

    def test_upsert_profile_increments_revision(self):
        self.db.register_agent("u1", "d1")
        p1 = self.db.upsert_profile("u1", "d1", '{}', "nanobot")
        self.assertEqual(p1["revision"], 1)
        p2 = self.db.upsert_profile("u1", "d1", '{"x":1}', "nanobot")
        self.assertEqual(p2["revision"], 2)

    def test_get_profile_not_found(self):
        self.assertIsNone(self.db.get_profile("u1", "d1"))

    def test_create_and_get_share(self):
        snapshot = json.dumps({"product": "nanobot", "resources": {"SOUL.md": "hi"}})
        self.db.create_share("tok1", "u1", "d1", "link", snapshot, "Xk9mQ2")
        share = self.db.get_share("tok1")
        self.assertIsNotNone(share)
        self.assertEqual(share["source_user_id"], "u1")
        self.assertEqual(share["snapshot"]["product"], "nanobot")
        self.assertEqual(share["short_code"], "Xk9mQ2")

    def test_list_shares_by_user(self):
        self.db.create_share("t1", "u1", "d1", "link", '{}', "aaa111")
        self.db.create_share("t2", "u1", "d2", "link", '{}', "bbb222")
        self.db.create_share("t3", "u2", "d1", "link", '{}', "ccc333")
        shares = self.db.list_shares_by_user("u1")
        self.assertEqual(len(shares), 2)

    def test_delete_share(self):
        self.db.create_share("tok1", "u1", "d1", "link", '{}', "ddd444")
        self.assertTrue(self.db.delete_share("tok1"))
        self.assertIsNone(self.db.get_share("tok1"))

    def test_get_share_by_code_db(self):
        self.db.create_share("tok1", "u1", "d1", "link", '{}', "Qw3rTy")
        share = self.db.get_share_by_code("Qw3rTy")
        self.assertIsNotNone(share)
        self.assertEqual(share["token"], "tok1")

    def test_profiles_by_user(self):
        self.db.register_agent("u1", "d1")
        self.db.register_agent("u1", "d2")
        self.db.upsert_profile("u1", "d1", '{}', "nanobot")
        self.db.upsert_profile("u1", "d2", '{}', "hermes")
        profiles = self.db.get_profiles_by_user("u1")
        self.assertEqual(len(profiles), 2)


class _TempAllowlist(ClawWorkspaceAllowlist):
    """Test allowlist pointing at a temp directory."""

    def __init__(self, root: Path):
        super().__init__()
        self._root = root

    @property
    def product_name(self) -> str:
        return "test"

    @property
    def default_workspace_root(self) -> Path:
        return self._root

    @property
    def patterns(self):
        return ["SOUL.md", "memory/*.md", "skills/*/SKILL.md"]


class TestAllowlist(unittest.TestCase):
    """Allowlist collect/apply correctness."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_collect_matches_patterns(self):
        (self.root / "SOUL.md").write_text("soul content")
        (self.root / "memory").mkdir()
        (self.root / "memory" / "MEMORY.md").write_text("mem content")
        (self.root / "ignored.txt").write_text("should not appear")

        al = _TempAllowlist(self.root)
        collected = al.collect()
        self.assertIn("SOUL.md", collected)
        self.assertIn("memory/MEMORY.md", collected)
        self.assertNotIn("ignored.txt", collected)

    def test_apply_creates_files(self):
        target = self.root / "apply_target"
        target.mkdir()
        al = _TempAllowlist(target)
        written = al.apply({"SOUL.md": "new soul", "memory/MEMORY.md": "new mem"})
        self.assertEqual(len(written), 2)
        self.assertEqual((target / "SOUL.md").read_text(), "new soul")
        self.assertEqual((target / "memory" / "MEMORY.md").read_text(), "new mem")

    def test_apply_rejects_path_traversal(self):
        al = _TempAllowlist(self.root)
        written = al.apply({"../../etc/passwd": "evil"})
        self.assertEqual(len(written), 0)

    def test_registry_contains_all_products(self):
        self.assertIn("nanobot", ALLOWLIST_REGISTRY)
        self.assertIn("openclaw", ALLOWLIST_REGISTRY)
        self.assertIn("hermes", ALLOWLIST_REGISTRY)
        self.assertIn("ms-agent", ALLOWLIST_REGISTRY)

    def test_ms_agent_single_agent_layout(self):
        """ms-agent is single-agent: no {name} placeholder, collects persona/
        memory/skills/config under ~/.ms_agent."""
        al = ALLOWLIST_REGISTRY["ms-agent"](local_dir=self.root)
        self.assertEqual(al.product_name, "ms-agent")
        # single-agent: no {name} placeholder in patterns
        self.assertFalse(any("{name}" in p for p in al.patterns))
        (self.root / "profile.md").write_text("p")
        (self.root / "MEMORY.md").write_text("m")
        (self.root / "facts.json").write_text("{}")
        (self.root / "settings.json").write_text("{}")
        (self.root / "skill.json").write_text("{}")
        (self.root / "random.txt").write_text("x")
        (self.root / "skills" / "foo").mkdir(parents=True)
        (self.root / "skills" / "foo" / "SKILL.md").write_text("s")
        got = al.collect()
        for f in ("profile.md", "MEMORY.md", "facts.json", "settings.json",
                  "skill.json", "skills/foo/SKILL.md"):
            self.assertIn(f, got)
        self.assertNotIn("random.txt", got)


class TestAllPathPrefix(unittest.TestCase):
    """split_all_path / join_all_path for cross-framework all-mode convert."""

    def _spec(self, fw):
        return ALLOWLIST_REGISTRY[fw](agent_name="all")

    def test_qwenpaw_split_join(self):
        spec = self._spec("qwenpaw")
        self.assertTrue(spec.is_root_per_agent)
        self.assertEqual(spec.split_all_path("bot-a/AGENTS.md"), ("bot-a", "AGENTS.md"))
        self.assertEqual(spec.split_all_path("default/SOUL.md"), ("default", "SOUL.md"))
        self.assertEqual(spec.split_all_path("README.md"), (None, "README.md"))
        self.assertEqual(spec.join_all_path("bot-a", "AGENTS.md"), "bot-a/AGENTS.md")

    def test_openclaw_split_join(self):
        spec = self._spec("openclaw")
        self.assertTrue(spec.is_root_per_agent)
        self.assertEqual(spec.split_all_path("workspace/AGENTS.md"), ("default", "AGENTS.md"))
        self.assertEqual(spec.split_all_path("workspace-bot-a/SOUL.md"), ("bot-a", "SOUL.md"))
        self.assertEqual(spec.split_all_path("README.md"), (None, "README.md"))
        self.assertEqual(spec.join_all_path("default", "AGENTS.md"), "workspace/AGENTS.md")
        self.assertEqual(spec.join_all_path("bot-a", "SOUL.md"), "workspace-bot-a/SOUL.md")

    def test_roundtrip_qwenpaw_to_openclaw(self):
        src = self._spec("qwenpaw")
        dst = self._spec("openclaw")
        agent, bare = src.split_all_path("bot-a/AGENTS.md")
        self.assertEqual(dst.join_all_path(agent, bare), "workspace-bot-a/AGENTS.md")

    def test_non_root_per_agent_passthrough(self):
        spec = self._spec("qoder")
        self.assertFalse(spec.is_root_per_agent)
        self.assertEqual(spec.split_all_path("agents/x.md"), (None, "agents/x.md"))
        self.assertEqual(spec.join_all_path("x", "agents/x.md"), "agents/x.md")


class TestHarnessBundle(unittest.TestCase):
    """Bundle serialization round-trip."""

    def test_round_trip(self):
        resources = {"SOUL.md": "soul", "memory/MEMORY.md": "mem"}
        bundle = HarnessBundle(
            product="nanobot",
            resources=resources,
            collected_at="2026-01-01T00:00:00",
        )
        raw = bundle.to_snapshot_json()
        restored = HarnessBundle.from_snapshot_json(raw)
        self.assertEqual(restored.product, "nanobot")
        self.assertEqual(restored.resources, resources)

    def test_skills_in_resources(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        (root / "skills" / "foo").mkdir(parents=True)
        (root / "skills" / "foo" / "SKILL.md").write_text("# Foo skill")
        (root / "SOUL.md").write_text("soul")

        al = _TempAllowlist(root)
        bundle = HarnessBundle.from_workspace(al)
        self.assertIn("skills/foo/SKILL.md", bundle.resources)
        tmp.cleanup()

    def test_to_resources_json(self):
        bundle = HarnessBundle("nanobot", {"a": "b"}, "2026-01-01")
        res_json = bundle.to_resources_json()
        self.assertEqual(json.loads(res_json), {"a": "b"})


class TestHarnessService(unittest.TestCase):
    """Integration tests for HarnessService."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self.tmp.name, "test.db"))
        self.svc = HarnessService(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sync_up_and_down(self):
        resources = {"SOUL.md": "I am helpful", "USER.md": "dev user"}
        profile = self.svc.sync_up("u1", "d1", "nanobot", resources)
        self.assertEqual(profile["revision"], 1)
        self.assertEqual(profile["resources"], resources)

        downloaded = self.svc.sync_down("u1", "d1")
        self.assertIsNotNone(downloaded)
        self.assertEqual(downloaded["resources"], resources)

    def test_sync_down_not_found(self):
        self.assertIsNone(self.svc.sync_down("u1", "d1"))

    def test_share_and_import(self):
        self.svc.sync_up("u1", "d1", "nanobot", {"SOUL.md": "soul A"})
        share = self.svc.create_share("u1", "d1")
        self.assertIn("token", share)
        self.assertIn("short_code", share)
        self.assertEqual(len(share["short_code"]), 6)

    def test_get_share_by_code(self):
        self.svc.sync_up("u1", "d1", "nanobot", {"SOUL.md": "soul"})
        share = self.svc.create_share("u1", "d1")
        found = self.svc.get_share_by_code(share["short_code"])
        self.assertIsNotNone(found)
        self.assertEqual(found["token"], share["token"])

    def test_get_share_by_code_not_found(self):
        self.assertIsNone(self.svc.get_share_by_code("ZZZZZZ"))

    def test_share_without_profile_raises(self):
        with self.assertRaises(ValueError):
            self.svc.create_share("u1", "d1")

    def test_list_and_delete_shares(self):
        self.svc.sync_up("u1", "d1", "nanobot", {"a": "b"})
        s1 = self.svc.create_share("u1", "d1")
        # Same agent_id returns the same share
        s2 = self.svc.create_share("u1", "d1")
        self.assertEqual(s1["token"], s2["token"])
        self.assertEqual(s1["short_code"], s2["short_code"])
        self.assertEqual(len(self.svc.list_shares("u1")), 1)
        self.assertTrue(self.svc.delete_share(s1["token"]))
        self.assertEqual(len(self.svc.list_shares("u1")), 0)

    def test_agent_lifecycle(self):
        self.svc.register_agent("u1", "d1", "My Laptop")
        agents = self.svc.list_agents("u1")
        self.assertEqual(len(agents), 1)
        self.assertTrue(self.svc.remove_agent("u1", "d1"))
        self.assertEqual(len(self.svc.list_agents("u1")), 0)


if __name__ == "__main__":
    unittest.main()
