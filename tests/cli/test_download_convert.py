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


class TestDownload(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "ws"
        _DownloadStub.instances = []

    def tearDown(self):
        self.tmp.cleanup()

    @mock.patch.object(commands.config, "resolve_username", return_value="u")
    @mock.patch.object(commands.config, "resolve_token", return_value="tok")
    @mock.patch.object(commands.config, "resolve_server", return_value="http://s")
    @mock.patch.object(commands, "UltronClient", _DownloadStub)
    def test_download_writes_files(self, *_):
        rc = _run([
            "download", "--name", "nano", "--framework", "nanobot",
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
            "download", "--name", "nano", "--framework", "nanobot",
            "--target", "hermes", "--local_dir", str(self.out),
        ])
        self.assertEqual(rc, 0)
        self.assertTrue((self.out / "memories" / "USER.md").is_file())
        self.assertFalse((self.out / "USER.md").is_file())

    @mock.patch.object(commands.config, "resolve_server", return_value=None)
    @mock.patch.object(commands.config, "resolve_token", return_value=None)
    def test_download_without_login_fails(self, *_):
        rc = _run(["download", "--name", "nano", "--framework", "nanobot",
                   "--local_dir", str(self.out)])
        self.assertEqual(rc, 1)


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
            "--local_dir", str(self.src), "--out", str(self.out),
        ])
        self.assertEqual(rc, 0)
        self.assertTrue((self.out / "SOUL.md").is_file())
        # nanobot USER.md maps to hermes memories/USER.md
        self.assertTrue((self.out / "memories" / "USER.md").is_file())

    def test_convert_dry_run_writes_nothing(self):
        rc = _run([
            "convert", "--from", "nanobot", "--to", "hermes",
            "--local_dir", str(self.src), "--out", str(self.out), "--dry-run",
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
