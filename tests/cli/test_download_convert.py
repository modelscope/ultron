# Copyright (c) ModelScope Contributors. All rights reserved.
"""CLI download (stubbed client) and local convert flows."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ultron.cli import build_parser
from ultron.cli import commands


def _run(argv):
    args = build_parser().parse_args(argv)
    return args.func(args)


class _DownloadStub:
    """Serves a fixed nanobot repo so download flows can be exercised offline."""

    instances = []
    STORE = {"SOUL.md": "soul", "USER.md": "user", "memory/MEMORY.md": "mem"}

    def __init__(self, server, token=None, timeout=60):
        _DownloadStub.instances.append(self)

    def repo_info(self, path, name):
        return {"Path": path, "Name": name, "Framework": "nanobot", "Revision": 1}

    def list_repo_files(self, path, name):
        return list(self.STORE)

    def download_repo_file(self, path, name, file_path):
        return self.STORE[file_path]


class _QwenpawAllStub:
    """Serves a qwenpaw all-mode repo (agent-prefixed paths) for convert tests."""

    instances = []
    STORE = {
        ".gitattributes": "x",
        "README.md": "readme",
        "default/AGENTS.md": "# default agents",
        "default/SOUL.md": "# default soul",
        "bot-a/AGENTS.md": "# bot-a agents",
        "bot-a/SOUL.md": "# bot-a soul",
        "bot-a/PROFILE.md": "# bot-a profile",
    }

    def __init__(self, server, token=None, timeout=60):
        _QwenpawAllStub.instances.append(self)

    def repo_info(self, path, name):
        return {"Path": path, "Name": name, "Framework": "qwenpaw", "Revision": 1}

    def list_repo_files(self, path, name):
        return list(self.STORE)

    def download_repo_file(self, path, name, file_path):
        return self.STORE[file_path]


class TestDownload(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "ws"
        _DownloadStub.instances = []
        _QwenpawAllStub.instances = []

    def tearDown(self):
        self.tmp.cleanup()

    @mock.patch.object(commands.config, "resolve_username", return_value="u")
    @mock.patch.object(commands.config, "resolve_token", return_value="tok")
    @mock.patch.object(commands.config, "resolve_server", return_value="http://s")
    @mock.patch.object(commands, "UltronClient", _DownloadStub)
    def test_download_writes_files(self, *_):
        rc = _run([
            "download", "--repo", "nano", "--framework", "nanobot",
            "--local_dir", str(self.out),
        ])
        self.assertEqual(rc, 0)
        self.assertEqual((self.out / "SOUL.md").read_text(), "soul")
        self.assertEqual((self.out / "memory" / "MEMORY.md").read_text(), "mem")

    @mock.patch.object(commands.config, "resolve_username", return_value="u")
    @mock.patch.object(commands.config, "resolve_token", return_value="tok")
    @mock.patch.object(commands.config, "resolve_server", return_value="http://s")
    @mock.patch.object(commands, "UltronClient", _DownloadStub)
    def test_download_with_conversion(self, *_):
        # nanobot -> hermes: USER.md must land at hermes' memories/USER.md.
        rc = _run([
            "download", "--repo", "nano", "--framework", "nanobot",
            "--target", "hermes", "--local_dir", str(self.out),
        ])
        self.assertEqual(rc, 0)
        self.assertTrue((self.out / "memories" / "USER.md").is_file())
        self.assertFalse((self.out / "USER.md").is_file())

    @mock.patch.object(commands.config, "resolve_server", return_value=None)
    @mock.patch.object(commands.config, "resolve_token", return_value=None)
    def test_download_without_login_fails(self, *_):
        rc = _run(["download", "--repo", "nano", "--framework", "nanobot",
                   "--local_dir", str(self.out)])
        self.assertEqual(rc, 1)

    def test_download_repo_required(self):
        """Download without --repo should fail at argparse level."""
        import sys
        from io import StringIO
        stderr = StringIO()
        with self.assertRaises(SystemExit):
            _run(["download", "--framework", "nanobot", "--local_dir", str(self.out)])

    @mock.patch.object(commands.config, "resolve_username", return_value="u")
    @mock.patch.object(commands.config, "resolve_token", return_value="tok")
    @mock.patch.object(commands.config, "resolve_server", return_value="http://s")
    @mock.patch.object(commands, "UltronClient", _DownloadStub)
    def test_download_with_name_creates_agent(self, *_):
        """Download with --name should write files for that local agent."""
        rc = _run([
            "download", "--repo", "nano", "--framework", "nanobot",
            "--name", "myagent", "--local_dir", str(self.out),
        ])
        self.assertEqual(rc, 0)
        # Files should still be written (nanobot shared files match).
        self.assertTrue((self.out / "SOUL.md").is_file())

    @mock.patch.object(commands.config, "resolve_username", return_value="u")
    @mock.patch.object(commands.config, "resolve_token", return_value="tok")
    @mock.patch.object(commands.config, "resolve_server", return_value="http://s")
    @mock.patch.object(commands, "UltronClient", _DownloadStub)
    def test_download_filters_by_allowlist(self, *_):
        """Files not matching the allowlist patterns should be skipped."""
        # Add a file that won't match any pattern.
        _DownloadStub.STORE = {
            "SOUL.md": "soul",
            "random/junk.txt": "junk",
            "memory/MEMORY.md": "mem",
        }
        rc = _run([
            "download", "--repo", "nano", "--framework", "nanobot",
            "--local_dir", str(self.out),
        ])
        self.assertEqual(rc, 0)
        # random/junk.txt should NOT be written.
        self.assertFalse((self.out / "random" / "junk.txt").exists())
        # Valid files should be written.
        self.assertTrue((self.out / "SOUL.md").is_file())
        # Restore original store.
        _DownloadStub.STORE = {"SOUL.md": "soul", "USER.md": "user", "memory/MEMORY.md": "mem"}

    @mock.patch.object(commands.config, "resolve_username", return_value="u")
    @mock.patch.object(commands.config, "resolve_token", return_value="tok")
    @mock.patch.object(commands.config, "resolve_server", return_value="http://s")
    @mock.patch.object(commands, "UltronClient", _DownloadStub)
    def test_download_repo_with_slash(self, *_):
        """--repo with '/' uses the specified group instead of username."""
        rc = _run([
            "download", "--repo", "othergroup/nano", "--framework", "nanobot",
            "--local_dir", str(self.out),
        ])
        self.assertEqual(rc, 0)
        # Should still write files (stub doesn't care about group).
        self.assertTrue((self.out / "SOUL.md").is_file())

    @mock.patch.object(commands.config, "resolve_username", return_value="u")
    @mock.patch.object(commands.config, "resolve_token", return_value="tok")
    @mock.patch.object(commands.config, "resolve_server", return_value="http://s")
    @mock.patch.object(commands, "UltronClient", _QwenpawAllStub)
    def test_download_convert_all_root_to_root(self, *_):
        """qwenpaw -> openclaw with --name all: per-agent convert + re-prefix."""
        rc = _run([
            "download", "--repo", "qw", "--framework", "qwenpaw",
            "--name", "all", "--target", "openclaw", "--local_dir", str(self.out),
        ])
        self.assertEqual(rc, 0)
        # default -> workspace/, bot-a -> workspace-bot-a/ (openclaw convention)
        self.assertTrue((self.out / "workspace" / "AGENTS.md").is_file())
        self.assertTrue((self.out / "workspace-bot-a" / "AGENTS.md").is_file())
        self.assertTrue((self.out / "workspace-bot-a" / "SOUL.md").is_file())
        # qwenpaw-only PROFILE.md has no openclaw equivalent: must NOT land as-is.
        self.assertFalse((self.out / "workspace-bot-a" / "PROFILE.md").exists())
        # top-level non-agent files (README) are dropped, never mis-prefixed.
        self.assertFalse((self.out / "README.md").exists())

    @mock.patch.object(commands.config, "resolve_username", return_value="u")
    @mock.patch.object(commands.config, "resolve_token", return_value="tok")
    @mock.patch.object(commands.config, "resolve_server", return_value="http://s")
    @mock.patch.object(commands, "UltronClient", _QwenpawAllStub)
    def test_download_convert_all_cross_layout_rejected(self, *_):
        """qwenpaw -> qoder with --name all is cross-layout: must be rejected."""
        rc = _run([
            "download", "--repo", "qw", "--framework", "qwenpaw",
            "--name", "all", "--target", "qoder", "--local_dir", str(self.out),
        ])
        self.assertEqual(rc, 1)

    @mock.patch.object(commands.config, "resolve_username", return_value="u")
    @mock.patch.object(commands.config, "resolve_token", return_value="tok")
    @mock.patch.object(commands.config, "resolve_server", return_value="http://s")
    @mock.patch.object(commands, "UltronClient", _QwenpawAllStub)
    def test_download_all_same_framework_keeps_prefixed_paths(self, *_):
        """qwenpaw -> qwenpaw with --name all: no convert, agent prefixes kept."""
        rc = _run([
            "download", "--repo", "qw", "--framework", "qwenpaw",
            "--name", "all", "--local_dir", str(self.out),
        ])
        self.assertEqual(rc, 0)
        self.assertTrue((self.out / "default" / "AGENTS.md").is_file())
        self.assertTrue((self.out / "bot-a" / "AGENTS.md").is_file())
        self.assertTrue((self.out / "bot-a" / "PROFILE.md").is_file())
        # non-spec top-level files are skipped.
        self.assertFalse((self.out / "README.md").exists())


class TestConvert(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = Path(self.tmp.name) / "nb"
        self.out = Path(self.tmp.name) / "hm"
        (self.src / "memory").mkdir(parents=True)
        (self.src / "SOUL.md").write_text("nano soul")
        (self.src / "USER.md").write_text("about user")
        (self.src / "memory" / "MEMORY.md").write_text("fact")

    def tearDown(self):
        self.tmp.cleanup()

    def test_convert_local_nanobot_to_hermes(self):
        rc = _run([
            "convert", "--from", "nanobot", "--to", "hermes",
            "--local_dir", str(self.src), "--out-dir", str(self.out),
        ])
        self.assertEqual(rc, 0)
        self.assertTrue((self.out / "SOUL.md").is_file())
        # nanobot USER.md maps to hermes memories/USER.md
        self.assertTrue((self.out / "memories" / "USER.md").is_file())

    def test_convert_dry_run_writes_nothing(self):
        rc = _run([
            "convert", "--from", "nanobot", "--to", "hermes",
            "--local_dir", str(self.src), "--out-dir", str(self.out), "--dry-run",
        ])
        self.assertEqual(rc, 0)
        self.assertFalse(self.out.exists())

    def test_convert_unknown_framework_fails(self):
        rc = _run([
            "convert", "--from", "nope", "--to", "hermes",
            "--local_dir", str(self.src),
        ])
        self.assertEqual(rc, 1)

    def test_convert_no_source_files_fails(self):
        rc = _run([
            "convert", "--from", "nanobot", "--to", "hermes",
            "--local_dir", str(self.src / "missing"),
        ])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
