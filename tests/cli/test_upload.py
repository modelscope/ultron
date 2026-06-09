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
        self.commits = []
        self.exists = False
        _StubClient.instances.append(self)

    def check_repo(self, path, name):
        return self.exists

    def create_repo(self, path, name, framework):
        self.created.append((path, name, framework))
        return {"success": True}

    def commit(self, path, name, actions, message):
        self.commits.append({"path": path, "name": name, "actions": actions})
        return {"success": True, "data": {"Revision": 1, "files": len(actions)}}


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

    def test_list_agents(self):
        rc = _run([
            "upload", "--framework", "qoder", "--list",
            "--local_dir", str(self.root),
        ])
        self.assertEqual(rc, 0)

    @mock.patch.object(commands.config, "resolve_username", return_value="u")
    @mock.patch.object(commands.config, "resolve_token", return_value="tok")
    @mock.patch.object(commands.config, "resolve_server", return_value="http://s")
    @mock.patch.object(commands, "UltronClient", _StubClient)
    def test_full_upload_creates_then_commits(self, *_):
        rc = _run([
            "upload", "--framework", "qoder", "--name", "reviewer",
            "--local_dir", str(self.root),
        ])
        self.assertEqual(rc, 0)
        self.assertEqual(len(_StubClient.instances), 1)
        client = _StubClient.instances[0]
        self.assertEqual(client.created, [("u", "reviewer", "qoder")])
        self.assertEqual(len(client.commits), 1)
        paths = {a["path"] for a in client.commits[0]["actions"]}
        self.assertEqual(paths, {"agents/reviewer.md", "AGENTS.md"})

    @mock.patch.object(commands.config, "resolve_server", return_value=None)
    @mock.patch.object(commands.config, "resolve_token", return_value=None)
    def test_upload_without_login_fails(self, *_):
        rc = _run([
            "upload", "--framework", "qoder", "--name", "reviewer",
            "--local_dir", str(self.root),
        ])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
