# Copyright (c) ModelScope Contributors. All rights reserved.
"""CLI argument parsing and upload flow (against a stubbed client)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ultron.cli import build_parser
from ultron.cli import commands


class _StubClient:
    """Records calls so the test can assert the upload flow."""

    instances = []

    def __init__(self, server, token=None, timeout=60):
        self.server = server
        self.token = token
        self.created = []
        self.uploaded_resources = None
        _StubClient.instances.append(self)

    def check_repo(self, path, name):
        return False

    def upload_file(self, resources):
        """Accept Dict[str, bytes]; return a fake Gid."""
        self.uploaded_resources = resources
        return "fake-gid-uuid"

    def create_repo(self, path, name, framework, **kwargs):
        self.created.append((path, name, framework, kwargs.get("system_prompt_files")))
        return {"success": True}


def _run(argv):
    args = build_parser().parse_args(argv)
    return args.func(args)


class TestUploadCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "agents").mkdir()
        (self.root / "agents" / "reviewer.md").write_text("reviewer")
        (self.root / "AGENTS.md").write_text("shared")
        (self.root / "skills" / "test-skill").mkdir(parents=True)
        (self.root / "skills" / "test-skill" / "SKILL.md").write_text("skill")
        _StubClient.instances = []

    def tearDown(self):
        self.tmp.cleanup()

    def test_unknown_framework_fails(self):
        rc = _run(["upload", "--framework", "nope", "--name", "x"])
        self.assertEqual(rc, 1)

    def test_dry_run_does_not_upload(self):
        rc = _run([
            "upload", "--framework", "qoder", "--name", "reviewer",
            "--local_dir", str(self.root), "--dry-run",
        ])
        self.assertEqual(rc, 0)
        self.assertEqual(_StubClient.instances, [])

    def test_no_files_fails(self):
        rc = _run([
            "upload", "--framework", "qoder", "--name", "ghost",
            "--local_dir", str(self.root / "empty"),
        ])
        self.assertEqual(rc, 1)

    @mock.patch.object(commands.config, "resolve_username", return_value="u")
    @mock.patch.object(commands.config, "resolve_token", return_value="tok")
    @mock.patch.object(commands.config, "resolve_server", return_value="http://s")
    @mock.patch.object(commands, "UltronClient", _StubClient)
    def test_full_upload_creates_then_uploads_zip(self, *_):
        rc = _run([
            "upload", "--framework", "qoder", "--name", "reviewer",
            "--local_dir", str(self.root),
        ])
        self.assertEqual(rc, 0)
        self.assertEqual(len(_StubClient.instances), 1)
        client = _StubClient.instances[0]
        # create_repo called with (group, repo_name, framework, system_prompt_files)
        self.assertEqual(len(client.created), 1)
        self.assertEqual(client.created[0][:3], ("u", "qoder-reviewer", "qoder"))
        self.assertEqual(client.created[0][3], "fake-gid-uuid")
        # Verify uploaded resources are bytes-valued dict
        self.assertIsNotNone(client.uploaded_resources)
        self.assertIsInstance(client.uploaded_resources, dict)
        self.assertIn("agents/reviewer.md", client.uploaded_resources)
        self.assertIn("AGENTS.md", client.uploaded_resources)
        # Values should be bytes
        for v in client.uploaded_resources.values():
            self.assertIsInstance(v, bytes)

    @mock.patch.object(commands.config, "resolve_server", return_value=None)
    @mock.patch.object(commands.config, "resolve_token", return_value=None)
    def test_upload_without_login_fails(self, *_):
        rc = _run([
            "upload", "--framework", "qoder", "--name", "reviewer",
            "--local_dir", str(self.root),
        ])
        self.assertEqual(rc, 1)

    # ---------- New tests for refactored behavior ----------

    @mock.patch.object(commands.config, "resolve_username", return_value="u")
    @mock.patch.object(commands.config, "resolve_token", return_value="tok")
    @mock.patch.object(commands.config, "resolve_server", return_value="http://s")
    @mock.patch.object(commands, "UltronClient", _StubClient)
    def test_upload_global_only_no_name(self, *_):
        """When --name is not specified and multiple agents exist, should fail."""
        # Add a second agent to trigger multiple-agent error.
        (self.root / "agents" / "coder.md").write_text("coder")
        rc = _run([
            "upload", "--framework", "qoder",
            "--local_dir", str(self.root),
        ])
        # Should fail because multiple sub-agents exist.
        self.assertEqual(rc, 1)

    @mock.patch.object(commands.config, "resolve_username", return_value="u")
    @mock.patch.object(commands.config, "resolve_token", return_value="tok")
    @mock.patch.object(commands.config, "resolve_server", return_value="http://s")
    @mock.patch.object(commands, "UltronClient", _StubClient)
    def test_upload_auto_select_single_agent(self, *_):
        """When only one sub-agent exists, auto-select it without --name."""
        rc = _run([
            "upload", "--framework", "qoder",
            "--local_dir", str(self.root),
        ])
        self.assertEqual(rc, 0)
        client = _StubClient.instances[0]
        # Should auto-select "reviewer" and upload as qoder-reviewer.
        self.assertEqual(client.created[0][1], "qoder-reviewer")

    @mock.patch.object(commands.config, "resolve_username", return_value="u")
    @mock.patch.object(commands.config, "resolve_token", return_value="tok")
    @mock.patch.object(commands.config, "resolve_server", return_value="http://s")
    @mock.patch.object(commands, "UltronClient", _StubClient)
    def test_upload_with_repo_slash(self, *_):
        """--repo with '/' should use the group from repo, not username."""
        rc = _run([
            "upload", "--framework", "qoder", "--name", "reviewer",
            "--repo", "mygroup/myrepo",
            "--local_dir", str(self.root),
        ])
        self.assertEqual(rc, 0)
        client = _StubClient.instances[0]
        # group should be "mygroup", repo should be "myrepo".
        self.assertEqual(client.created[0][0], "mygroup")
        self.assertEqual(client.created[0][1], "myrepo")

    @mock.patch.object(commands.config, "resolve_username", return_value="u")
    @mock.patch.object(commands.config, "resolve_token", return_value="tok")
    @mock.patch.object(commands.config, "resolve_server", return_value="http://s")
    @mock.patch.object(commands, "UltronClient", _StubClient)
    def test_upload_repo_defaults_to_name(self, *_):
        """When --repo is omitted, remote repo name derives from --name."""
        rc = _run([
            "upload", "--framework", "qoder", "--name", "reviewer",
            "--local_dir", str(self.root),
        ])
        self.assertEqual(rc, 0)
        client = _StubClient.instances[0]
        self.assertEqual(client.created[0][0], "u")
        self.assertEqual(client.created[0][1], "qoder-reviewer")

    @mock.patch.object(commands.config, "resolve_username", return_value="u")
    @mock.patch.object(commands.config, "resolve_token", return_value="tok")
    @mock.patch.object(commands.config, "resolve_server", return_value="http://s")
    @mock.patch.object(commands, "UltronClient", _StubClient)
    def test_upload_global_only_no_agents_dir(self, *_):
        """When no agents/ directory exists, upload only shared (global) files."""
        import shutil
        shutil.rmtree(self.root / "agents")
        rc = _run([
            "upload", "--framework", "qoder",
            "--local_dir", str(self.root),
        ])
        self.assertEqual(rc, 0)
        client = _StubClient.instances[0]
        # Repo should be "qoder" (no name specified, global mode).
        self.assertEqual(client.created[0][1], "qoder")
        # Verify that no agents/*.md files are uploaded.
        self.assertIsNotNone(client.uploaded_resources)
        for p in client.uploaded_resources.keys():
            self.assertFalse(p.startswith("agents/"))


class TestListCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "agents").mkdir()
        (self.root / "agents" / "reviewer.md").write_text("reviewer")
        (self.root / "agents" / "coder.md").write_text("coder")
        (self.root / "AGENTS.md").write_text("shared")

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_shows_agents(self):
        rc = _run(["list", "--framework", "qoder", "--local_dir", str(self.root)])
        self.assertEqual(rc, 0)

    def test_list_unknown_framework_fails(self):
        rc = _run(["list", "--framework", "nope", "--local_dir", str(self.root)])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
