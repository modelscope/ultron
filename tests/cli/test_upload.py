# Copyright (c) ModelScope Contributors. All rights reserved.
"""CLI argument parsing and upload flow (against a stubbed client)."""
import io
import tempfile
import unittest
import zipfile
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
        self.uploaded_zip = None
        _StubClient.instances.append(self)

    def check_repo(self, path, name):
        return False

    def upload_file(self, resources):
        """Accept either dict or bytes; return a fake file_id."""
        if isinstance(resources, dict):
            from ultron.cli.sync import zip_resources
            self.uploaded_zip = zip_resources(resources)
        else:
            self.uploaded_zip = resources
        return "fake-file-id"

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
    def test_full_upload_creates_then_uploads_zip(self, *_):
        rc = _run([
            "upload", "--framework", "qoder", "--name", "reviewer",
            "--local_dir", str(self.root),
        ])
        self.assertEqual(rc, 0)
        self.assertEqual(len(_StubClient.instances), 1)
        client = _StubClient.instances[0]
        # create_repo called with (path, name, framework, system_prompt_files)
        self.assertEqual(len(client.created), 1)
        self.assertEqual(client.created[0][:3], ("u", "qoder-reviewer", "qoder"))
        self.assertEqual(client.created[0][3], "fake-file-id")
        # Verify zip content
        self.assertIsNotNone(client.uploaded_zip)
        with zipfile.ZipFile(io.BytesIO(client.uploaded_zip)) as zf:
            paths = {p.removeprefix("agent/") for p in zf.namelist()}
        self.assertIn("agents/reviewer.md", paths)
        self.assertIn("AGENTS.md", paths)

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
