# Copyright (c) ModelScope Contributors. All rights reserved.
"""Sub-agent-aware allowlist collection."""
import tempfile
import unittest
from pathlib import Path

from ultron.services.harness.allowlist import (
    ALLOWLIST_REGISTRY,
    NanobotWorkspaceAllowlist,
    QoderWorkspaceAllowlist,
    QwenpawWorkspaceAllowlist,
)


class TestAgentAwareCollect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_qoder_collects_named_agent_plus_shared(self):
        (self.root / "agents").mkdir()
        (self.root / "agents" / "reviewer.md").write_text("reviewer agent")
        (self.root / "agents" / "other.md").write_text("other agent")
        (self.root / "AGENTS.md").write_text("shared instructions")
        (self.root / "skills" / "x").mkdir(parents=True)
        (self.root / "skills" / "x" / "SKILL.md").write_text("skill")

        spec = QoderWorkspaceAllowlist(agent_name="reviewer", local_dir=self.root)
        collected = spec.collect()

        self.assertIn("agents/reviewer.md", collected)
        self.assertIn("AGENTS.md", collected)
        self.assertIn("skills/x/SKILL.md", collected)
        # Only the selected sub-agent's file, not other agents.
        self.assertNotIn("agents/other.md", collected)

    def test_name_templating_is_isolated_per_agent(self):
        (self.root / "agents").mkdir()
        (self.root / "agents" / "a.md").write_text("a")
        (self.root / "agents" / "b.md").write_text("b")

        a = QoderWorkspaceAllowlist(agent_name="a", local_dir=self.root).collect()
        b = QoderWorkspaceAllowlist(agent_name="b", local_dir=self.root).collect()
        self.assertEqual(set(a), {"agents/a.md"})
        self.assertEqual(set(b), {"agents/b.md"})

    def test_qoder_list_agents(self):
        (self.root / "agents").mkdir()
        (self.root / "agents" / "a.md").write_text("a")
        (self.root / "agents" / "b.md").write_text("b")
        spec = QoderWorkspaceAllowlist(local_dir=self.root)
        self.assertEqual(spec.list_agents(), ["a", "b"])

    def test_qwenpaw_default_root_uses_agent_name(self):
        # default_workspace_root must embed the agent name under workspaces/.
        spec = QwenpawWorkspaceAllowlist(agent_name="browse-agent")
        self.assertTrue(
            str(spec.default_workspace_root).endswith("workspaces/browse-agent")
        )

    def test_local_dir_override_wins(self):
        (self.root / "SOUL.md").write_text("soul")
        (self.root / "agents").mkdir()
        (self.root / "agents" / "main.md").write_text("main")
        spec = NanobotWorkspaceAllowlist(agent_name="main", local_dir=self.root)
        self.assertEqual(spec.workspace_root, self.root)
        collected = spec.collect()
        self.assertIn("SOUL.md", collected)
        self.assertIn("agents/main.md", collected)

    def test_missing_root_returns_empty(self):
        spec = QoderWorkspaceAllowlist(
            agent_name="x", local_dir=self.root / "does-not-exist"
        )
        self.assertEqual(spec.collect(), {})

    def test_registry_includes_qoder(self):
        self.assertIn("qoder", ALLOWLIST_REGISTRY)


if __name__ == "__main__":
    unittest.main()
