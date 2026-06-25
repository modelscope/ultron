"""Integration tests for ``ultron watch`` bidirectional sync.

Tests run the REAL ``watch_loop`` in child processes (via multiprocessing),
make local and remote changes, wait for sync cycles, then send SIGTERM to
stop the watcher and verify results.

Scenarios covered:
    - qoder (file-per-agent + shared) with --name all: local→remote push
    - qoder all: remote→local pull
    - qwenpaw (root-per-agent) with --name all: bidirectional sync
    - qwenpaw with specific sub-agent: individual watch
    - Conflict resolution: both sides changed → remote wins + backup
    - Multi-process concurrent watches on different repos/frameworks
    - Delete propagation: local delete → remote, remote delete → local
    - First sync: empty baseline → initial push
    - No-op: nothing changed → state unchanged
    - file-per-agent watch guard
    - Add new file locally
    - State persistence

Usage:
    python -m unittest tests.api.test_watch_sync -v
    python tests/api/test_watch_sync.py
"""
import multiprocessing
import os
import shutil
import signal
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Dict

from ultron.cli import config as cli_config
from ultron.cli.cache import load_sync_state, save_sync_state, sync_state_file
from ultron.cli.client import ApiError, UltronClient
from ultron.services.harness.allowlist import (
    ALL_AGENT_NAME,
    ALLOWLIST_REGISTRY,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SERVER = os.environ.get("SERVER", "http://pre.modelscope.cn")
TOKEN = os.environ.get("TOKEN", "")
AGENT_PREFIX = "test-watch"
REQUEST_INTERVAL = int(os.environ.get("REQUEST_INTERVAL", "8"))

# Short interval for watch loops in tests (seconds)
WATCH_INTERVAL = 5


def _wait(seconds: int = 5):
    print(f"    (waiting {seconds}s...)")
    time.sleep(seconds)


# ---------------------------------------------------------------------------
# Child process target: runs the real watch_loop
# ---------------------------------------------------------------------------

def _watch_process_target(
    server: str,
    token: str,
    data_dir: str,
    framework: str,
    agent_name: str,
    local_dir: str,
    repo_name: str,
    interval: int,
    push_only: bool = True,
):
    """Run watch_loop in a child process. Stopped by SIGTERM."""
    # Set data dir so cache/state files go to the right place
    os.environ["ULTRON_DATA_DIR"] = data_dir

    from ultron.cli.client import UltronClient
    from ultron.cli.watcher import watch_loop
    from ultron.services.harness.allowlist import ALLOWLIST_REGISTRY

    spec_cls = ALLOWLIST_REGISTRY[framework]
    spec = spec_cls(agent_name=agent_name, local_dir=Path(local_dir))
    client = UltronClient(server, token)
    username = client.login(token)

    watch_loop(spec, client, username, repo_name, framework, interval=interval, push_only=push_only)


# ===========================================================================
# Test case
# ===========================================================================

class TestWatchSync(unittest.TestCase):
    """Integration tests for bidirectional watch sync using real watch_loop."""

    client: UltronClient = None  # type: ignore
    username: str = ""
    _data_dir: str = ""

    @classmethod
    def setUpClass(cls):
        cls.client = UltronClient(SERVER)
        cls.username = cls.client.login(TOKEN)
        assert cls.username, "login failed"
        print(f"    Logged in as {cls.username}")
        # Shared data dir for all tests
        cls._data_dir = tempfile.mkdtemp(prefix="ultron_test_watch_data_")
        os.environ["ULTRON_DATA_DIR"] = cls._data_dir
        cli_config.save(SERVER, cls.username, TOKEN)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("ULTRON_DATA_DIR", None)
        shutil.rmtree(cls._data_dir, ignore_errors=True)

    def setUp(self):
        time.sleep(REQUEST_INTERVAL)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------
    def _create_local(self, files: dict) -> str:
        """Write files into a temp dir, return path."""
        tmpdir = tempfile.mkdtemp(prefix="ultron_test_watch_")
        for rel, content in files.items():
            fp = Path(tmpdir) / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")
        return tmpdir

    def _cleanup(self, path: str):
        shutil.rmtree(path, ignore_errors=True)

    def _upload_remote(self, name: str, framework: str, files: dict):
        """Upload files directly to remote (simulates remote-side changes)."""
        file_id = self.client.upload_file(files)
        self.client.create_repo(self.username, name, framework, system_prompt_files=file_id)

    def _start_watch(self, framework: str, agent_name: str, local_dir: str, repo_name: str, push_only: bool = True) -> multiprocessing.Process:
        """Start a watch_loop in a child process, return the Process."""
        p = multiprocessing.Process(
            target=_watch_process_target,
            args=(SERVER, TOKEN, self._data_dir, framework, agent_name, local_dir, repo_name, WATCH_INTERVAL, push_only),
            daemon=True,
        )
        p.start()
        return p

    def _stop_watch(self, proc: multiprocessing.Process, timeout: int = 15):
        """Send SIGTERM to stop the watch process."""
        if proc.is_alive():
            os.kill(proc.pid, signal.SIGTERM)
            proc.join(timeout=timeout)
        if proc.is_alive():
            proc.terminate()

    def _wait_cycles(self, n: int = 2):
        """Wait for n watch cycles to complete."""
        time.sleep(WATCH_INTERVAL * n + 5)

    # -----------------------------------------------------------------------
    # 01. qoder all: local change → push to remote
    # -----------------------------------------------------------------------
    def test_01_qoder_all_local_push(self):
        """Local file change should be pushed to remote via watch_loop."""
        repo_name = f"{AGENT_PREFIX}-qoder-push"
        files = {
            "AGENTS.md": "# Agents\nInitial version.\n",
            "agents/reviewer.md": "# Reviewer\nReview code.\n",
            "rules/style.md": "# Style\nUse 4 spaces.\n",
        }
        local_dir = self._create_local(files)
        proc = None
        try:
            proc = self._start_watch("qoder", ALL_AGENT_NAME, local_dir, repo_name)
            # Wait for initial push
            self._wait_cycles(2)

            # Verify remote has the files
            remote = self.client.list_repo_files(self.username, repo_name)
            self.assertIn("AGENTS.md", remote)
            self.assertIn("agents/reviewer.md", remote)

            # Modify a local file
            (Path(local_dir) / "AGENTS.md").write_text("# Agents\nUpdated version.\n", encoding="utf-8")

            # Wait for sync to push
            self._wait_cycles(2)

            # Verify remote content updated
            content = self.client.download_repo_file(self.username, repo_name, "AGENTS.md")
            self.assertIn("Updated version", content)
        finally:
            if proc:
                self._stop_watch(proc)
            self._cleanup(local_dir)

    # -----------------------------------------------------------------------
    # 02. qoder all: remote change → pull to local (bidirectional mode)
    # -----------------------------------------------------------------------
    def test_02_qoder_all_remote_pull(self):
        """Remote change should be pulled to local via watch_loop (push_only=False)."""
        repo_name = f"{AGENT_PREFIX}-qoder-pull"
        files = {
            "AGENTS.md": "# Agents\nOriginal.\n",
            "agents/coder.md": "# Coder\nWrite code.\n",
            "commands/build.md": "# Build\nBuild project.\n",
        }
        local_dir = self._create_local(files)
        proc = None
        try:
            proc = self._start_watch("qoder", ALL_AGENT_NAME, local_dir, repo_name, push_only=False)
            self._wait_cycles(2)

            # Simulate remote change
            updated_files = dict(files)
            updated_files["AGENTS.md"] = "# Agents\nRemotely modified.\n"
            updated_files["commands/deploy.md"] = "# Deploy\nNew remote file.\n"
            self._upload_remote(repo_name, "qoder", updated_files)
            _wait(5)

            # Wait for pull
            self._wait_cycles(2)

            # Verify local got the update
            local_content = (Path(local_dir) / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Remotely modified", local_content)
            # New file should appear locally
            new_file = Path(local_dir) / "commands" / "deploy.md"
            self.assertTrue(new_file.exists(), "new remote file should be pulled")
        finally:
            if proc:
                self._stop_watch(proc)
            self._cleanup(local_dir)

    # -----------------------------------------------------------------------
    # 03. qwenpaw all: bidirectional sync (push_only=False)
    # -----------------------------------------------------------------------
    def test_03_qwenpaw_all_bidirectional(self):
        """qwenpaw all mode: local push then remote pull via watch_loop (push_only=False)."""
        repo_name = f"{AGENT_PREFIX}-qwenpaw-bi"
        files = {
            "bot-a/SOUL.md": "# Soul\nBot A identity.\n",
            "bot-a/PROFILE.md": "# Profile\nBot A profile.\n",
            "bot-b/SOUL.md": "# Soul\nBot B identity.\n",
        }
        local_dir = self._create_local(files)
        proc = None
        try:
            proc = self._start_watch("qwenpaw", ALL_AGENT_NAME, local_dir, repo_name, push_only=False)
            self._wait_cycles(2)

            # Verify push happened
            remote = self.client.list_repo_files(self.username, repo_name)
            self.assertIn("bot-a/SOUL.md", remote)
            self.assertIn("bot-b/SOUL.md", remote)

            # Remote adds a new file
            updated_files = dict(files)
            updated_files["bot-a/MEMORY.md"] = "# Memory\nBot A learned something.\n"
            self._upload_remote(repo_name, "qwenpaw", updated_files)
            _wait(5)

            # Wait for pull
            self._wait_cycles(2)

            # Verify local has new file
            mem_file = Path(local_dir) / "bot-a" / "MEMORY.md"
            self.assertTrue(mem_file.exists())
            self.assertIn("learned something", mem_file.read_text(encoding="utf-8"))
        finally:
            if proc:
                self._stop_watch(proc)
            self._cleanup(local_dir)

    # -----------------------------------------------------------------------
    # 04. qwenpaw individual sub-agent watch
    # -----------------------------------------------------------------------
    def test_04_qwenpaw_individual_watch(self):
        """qwenpaw supports watching a specific sub-agent via watch_loop."""
        repo_name = f"{AGENT_PREFIX}-qwenpaw-ind"
        files = {
            "SOUL.md": "# Soul\nMy bot identity.\n",
            "PROFILE.md": "# Profile\nCreative writer.\n",
        }
        local_dir = self._create_local(files)
        proc = None
        try:
            proc = self._start_watch("qwenpaw", repo_name, local_dir, repo_name)
            self._wait_cycles(2)

            # Verify initial push
            remote = self.client.list_repo_files(self.username, repo_name)
            self.assertIn("SOUL.md", remote)

            # Modify local
            (Path(local_dir) / "PROFILE.md").write_text(
                "# Profile\nCreative writer. Loves sci-fi.\n", encoding="utf-8"
            )

            # Wait for push
            self._wait_cycles(2)

            # Verify remote updated
            content = self.client.download_repo_file(self.username, repo_name, "PROFILE.md")
            self.assertIn("Loves sci-fi", content)
        finally:
            if proc:
                self._stop_watch(proc)
            self._cleanup(local_dir)

    # -----------------------------------------------------------------------
    # 05. Conflict: both sides changed → remote wins (push_only=False)
    # -----------------------------------------------------------------------
    def test_05_conflict_remote_wins(self):
        """When both local and remote change, remote should win (push_only=False)."""
        repo_name = f"{AGENT_PREFIX}-conflict"
        files = {
            "AGENTS.md": "# Agents\nBaseline.\n",
            "rules/naming.md": "# Naming\nUse snake_case.\n",
        }
        local_dir = self._create_local(files)
        proc = None
        try:
            # Pre-upload to ensure remote matches local (clean starting point)
            self._upload_remote(repo_name, "qoder", files)
            _wait(8)

            proc = self._start_watch("qoder", ALL_AGENT_NAME, local_dir, repo_name, push_only=False)
            self._wait_cycles(2)

            # Stop watch temporarily to make simultaneous changes
            self._stop_watch(proc)
            proc = None
            _wait(REQUEST_INTERVAL)

            # Remote: modify AGENTS.md
            remote_files = dict(files)
            remote_files["AGENTS.md"] = "# Agents\nRemote version wins.\n"
            self._upload_remote(repo_name, "qoder", remote_files)
            _wait(8)

            # Local: modify AGENTS.md differently
            (Path(local_dir) / "AGENTS.md").write_text(
                "# Agents\nLocal version loses.\n", encoding="utf-8"
            )

            # Restart watch — should detect conflict and pull remote
            proc = self._start_watch("qoder", ALL_AGENT_NAME, local_dir, repo_name, push_only=False)
            self._wait_cycles(3)

            # Verify local has REMOTE content (remote wins)
            local_content = (Path(local_dir) / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Remote version wins", local_content)
        finally:
            if proc:
                self._stop_watch(proc)
            self._cleanup(local_dir)

    # -----------------------------------------------------------------------
    # 06. Delete propagation: local delete → remote
    # -----------------------------------------------------------------------
    def test_06_local_delete_pushes(self):
        """Deleting a local file should remove it from remote via watch_loop."""
        repo_name = f"{AGENT_PREFIX}-del-local"
        files = {
            "AGENTS.md": "# Agents\nKeep this.\n",
            "rules/obsolete.md": "# Obsolete\nRemove me.\n",
        }
        local_dir = self._create_local(files)
        proc = None
        try:
            # Pre-upload to ensure remote matches local (avoids conflict on first sync)
            self._upload_remote(repo_name, "qoder", files)
            _wait(8)

            proc = self._start_watch("qoder", ALL_AGENT_NAME, local_dir, repo_name)
            self._wait_cycles(2)

            # Verify both files on remote
            remote = self.client.list_repo_files(self.username, repo_name)
            self.assertIn("rules/obsolete.md", remote)

            # Delete local file
            (Path(local_dir) / "rules" / "obsolete.md").unlink()

            # Wait for sync to push the deletion
            self._wait_cycles(2)

            # Verify remote no longer has it
            remote = self.client.list_repo_files(self.username, repo_name)
            self.assertNotIn("rules/obsolete.md", remote)
            self.assertIn("AGENTS.md", remote)
        finally:
            if proc:
                self._stop_watch(proc)
            self._cleanup(local_dir)

    # -----------------------------------------------------------------------
    # 07. Delete propagation: remote delete → local (push_only=False)
    # -----------------------------------------------------------------------
    def test_07_remote_delete_pulls(self):
        """Remote file removal should delete local file via watch_loop (push_only=False)."""
        repo_name = f"{AGENT_PREFIX}-del-remote"
        files = {
            "AGENTS.md": "# Agents\nStay.\n",
            "commands/temp.md": "# Temp\nWill be removed remotely.\n",
        }
        local_dir = self._create_local(files)
        proc = None
        try:
            proc = self._start_watch("qoder", ALL_AGENT_NAME, local_dir, repo_name, push_only=False)
            self._wait_cycles(2)

            # Remote removes a file (re-upload without it)
            reduced_files = {"AGENTS.md": "# Agents\nStay.\n"}
            self._upload_remote(repo_name, "qoder", reduced_files)
            _wait(8)

            # Wait for pull (file-set comparison detects deletion)
            self._wait_cycles(2)

            temp_path = Path(local_dir) / "commands" / "temp.md"
            self.assertFalse(temp_path.exists(), "locally deleted file should be gone")
            self.assertTrue((Path(local_dir) / "AGENTS.md").exists())
        finally:
            if proc:
                self._stop_watch(proc)
            self._cleanup(local_dir)

    # -----------------------------------------------------------------------
    # 08. Multi-process: concurrent watches on different repos (push_only=False)
    # -----------------------------------------------------------------------
    def test_08_multi_process_concurrent_watches(self):
        """Multiple watch processes for different repos sync independently."""
        repo1 = f"{AGENT_PREFIX}-mt-qoder"
        files1 = {
            "AGENTS.md": "# MT1\nMulti-thread test 1.\n",
            "agents/bot1.md": "# Bot1\nFirst bot.\n",
        }
        local1 = self._create_local(files1)

        repo2 = f"{AGENT_PREFIX}-mt-qwenpaw"
        files2 = {
            "SOUL.md": "# MT2\nMulti-thread test 2.\n",
            "PROFILE.md": "# Profile\nSecond bot.\n",
        }
        local2 = self._create_local(files2)

        proc1 = None
        proc2 = None
        try:
            proc1 = self._start_watch("qoder", ALL_AGENT_NAME, local1, repo1, push_only=False)
            proc2 = self._start_watch("qwenpaw", repo2, local2, repo2, push_only=False)

            # Wait for initial push
            self._wait_cycles(3)

            # Make local change to repo1
            (Path(local1) / "AGENTS.md").write_text(
                "# MT1\nUpdated by watch process.\n", encoding="utf-8"
            )

            # Make remote change to repo2
            updated2 = dict(files2)
            updated2["SOUL.md"] = "# MT2\nRemotely updated.\n"
            self._upload_remote(repo2, "qwenpaw", updated2)

            # Wait for sync cycles
            self._wait_cycles(3)

            # Verify repo1 remote got the local update
            content1 = self.client.download_repo_file(self.username, repo1, "AGENTS.md")
            self.assertIn("Updated by watch process", content1)

            # Verify repo2 local got the remote update
            soul2 = (Path(local2) / "SOUL.md").read_text(encoding="utf-8")
            self.assertIn("Remotely updated", soul2)
        finally:
            if proc1:
                self._stop_watch(proc1)
            if proc2:
                self._stop_watch(proc2)
            self._cleanup(local1)
            self._cleanup(local2)

    # -----------------------------------------------------------------------
    # 09. First sync with empty baseline → push everything
    # -----------------------------------------------------------------------
    def test_09_first_sync_empty_baseline(self):
        """First watch start with no prior state should push all local files."""
        repo_name = f"{AGENT_PREFIX}-first-sync"
        files = {
            "SOUL.md": "# Soul\nBrand new agent.\n",
            "PROFILE.md": "# Profile\nNew profile.\n",
        }
        local_dir = self._create_local(files)
        proc = None
        try:
            # Ensure no prior state
            sf = sync_state_file(repo_name)
            if sf.exists():
                sf.unlink()

            proc = self._start_watch("qwenpaw", repo_name, local_dir, repo_name)
            self._wait_cycles(2)

            # Verify remote has files
            remote = self.client.list_repo_files(self.username, repo_name)
            self.assertIn("SOUL.md", remote)
            self.assertIn("PROFILE.md", remote)
        finally:
            if proc:
                self._stop_watch(proc)
            self._cleanup(local_dir)

    # -----------------------------------------------------------------------
    # 10. No-op cycle: nothing changed
    # -----------------------------------------------------------------------
    def test_10_noop_no_changes(self):
        """When nothing changed, watch_loop should not modify files."""
        repo_name = f"{AGENT_PREFIX}-noop"
        files = {"SOUL.md": "# Soul\nStable content.\n"}
        local_dir = self._create_local(files)
        proc = None
        try:
            proc = self._start_watch("qwenpaw", repo_name, local_dir, repo_name)
            # Wait for initial push
            self._wait_cycles(2)

            # Record local file mtime
            soul_path = Path(local_dir) / "SOUL.md"
            mtime_before = soul_path.stat().st_mtime

            # Wait several more cycles (no changes)
            self._wait_cycles(2)

            # File should not have been touched
            mtime_after = soul_path.stat().st_mtime
            self.assertEqual(mtime_before, mtime_after, "file should not be modified in no-op")
        finally:
            if proc:
                self._stop_watch(proc)
            self._cleanup(local_dir)

    # -----------------------------------------------------------------------
    # 11. file-per-agent watch guard: qoder individual → rejected
    # -----------------------------------------------------------------------
    def test_11_qoder_individual_watch_rejected(self):
        """qoder individual watch (not 'all') should be blocked by cmd_watch."""
        from ultron.cli.commands import cmd_watch

        args = SimpleNamespace(
            framework="qoder",
            name="reviewer",
            local_dir=None,
            server=SERVER,
            token=TOKEN,
            interval=60,
            sessions_dir=None,
        )
        rc = cmd_watch(args)
        self.assertEqual(rc, 1, "qoder individual watch should be rejected")

    # -----------------------------------------------------------------------
    # 12. qwenpaw individual watch → allowed
    # -----------------------------------------------------------------------
    def test_12_qwenpaw_individual_watch_allowed(self):
        """qwenpaw supports individual sub-agent watch (supports_individual_watch=True)."""
        spec_cls = ALLOWLIST_REGISTRY["qwenpaw"]
        spec = spec_cls(agent_name="test-bot")
        self.assertTrue(spec.supports_individual_watch)

    # -----------------------------------------------------------------------
    # 13. Add new file locally → appears on remote
    # -----------------------------------------------------------------------
    def test_13_add_new_file_locally(self):
        """Adding a new file locally should push it to remote via watch_loop."""
        repo_name = f"{AGENT_PREFIX}-add-file"
        files = {"SOUL.md": "# Soul\nBase.\n"}
        local_dir = self._create_local(files)
        proc = None
        try:
            proc = self._start_watch("qwenpaw", repo_name, local_dir, repo_name)
            self._wait_cycles(2)

            # Add new file locally
            new_path = Path(local_dir) / "MEMORY.md"
            new_path.write_text("# Memory\nSomething new.\n", encoding="utf-8")

            # Wait for sync
            self._wait_cycles(2)

            remote = self.client.list_repo_files(self.username, repo_name)
            self.assertIn("MEMORY.md", remote)
            content = self.client.download_repo_file(self.username, repo_name, "MEMORY.md")
            self.assertIn("Something new", content)
        finally:
            if proc:
                self._stop_watch(proc)
            self._cleanup(local_dir)

    # -----------------------------------------------------------------------
    # 14. Sync state persistence across restarts
    # -----------------------------------------------------------------------
    def test_14_state_persistence(self):
        """Sync state persists to disk — second watch start reuses baseline."""
        repo_name = f"{AGENT_PREFIX}-persist"
        files = {"SOUL.md": "# Soul\nPersist test.\n"}
        local_dir = self._create_local(files)
        proc = None
        try:
            # First watch: push and build baseline
            proc = self._start_watch("qwenpaw", repo_name, local_dir, repo_name)
            self._wait_cycles(2)
            self._stop_watch(proc)
            proc = None

            # Check state was persisted
            state = load_sync_state(repo_name)
            self.assertGreater(state["last_commit_date"], 0)
            self.assertIn("SOUL.md", state["remote_files"])

            _wait(REQUEST_INTERVAL)

            # Second watch: no changes → should be no-op (file not modified)
            soul_path = Path(local_dir) / "SOUL.md"
            mtime_before = soul_path.stat().st_mtime

            proc = self._start_watch("qwenpaw", repo_name, local_dir, repo_name)
            self._wait_cycles(2)

            mtime_after = soul_path.stat().st_mtime
            self.assertEqual(mtime_before, mtime_after)
        finally:
            if proc:
                self._stop_watch(proc)
            self._cleanup(local_dir)
            sf = sync_state_file(repo_name)
            if sf.exists():
                sf.unlink()


    # -----------------------------------------------------------------------
    # 15. All files share a common prefix (e.g. skills/) → wrapper prevents
    #     server from stripping the prefix
    # -----------------------------------------------------------------------
    def test_15_common_prefix_preserved(self):
        """When ALL files share a top-level prefix, the zip wrapper ensures
        the server does not strip that prefix after upload.

        Without the wrapper, zip entries like skills/lint/SKILL.md would lose
        the 'skills/' prefix after the server strips the first directory level.
        With the wrapper, entries become agent/skills/lint/SKILL.md; the server
        strips 'agent/' and the real path (skills/...) is preserved.
        """
        repo_name = f"{AGENT_PREFIX}-prefix"
        # All files share the 'skills/' top-level prefix
        files = {
            "skills/lint/SKILL.md": "# Lint\nRun linter.\n",
            "skills/lint/scripts/run.sh": "#!/bin/bash\nflake8 .\n",
            "skills/format/SKILL.md": "# Format\nAuto-format code.\n",
        }
        local_dir = self._create_local(files)
        proc = None
        try:
            proc = self._start_watch("qoder", ALL_AGENT_NAME, local_dir, repo_name)
            self._wait_cycles(2)

            # Verify remote paths retain the 'skills/' prefix
            remote = self.client.list_repo_files(self.username, repo_name)
            self.assertIn("skills/lint/SKILL.md", remote,
                          "skills/ prefix must be preserved on server")
            self.assertIn("skills/lint/scripts/run.sh", remote)
            self.assertIn("skills/format/SKILL.md", remote)

            # Verify content
            content = self.client.download_repo_file(
                self.username, repo_name, "skills/lint/SKILL.md")
            self.assertIn("Run linter", content)
        finally:
            if proc:
                self._stop_watch(proc)
            self._cleanup(local_dir)

    # -----------------------------------------------------------------------
    # 16. Modify a file under common prefix → remote update preserves path
    # -----------------------------------------------------------------------
    def test_16_common_prefix_modify_push(self):
        """Modify a file under a shared prefix, verify the push preserves
        full paths on the server (regression for zip wrapper)."""
        repo_name = f"{AGENT_PREFIX}-prefix-mod"
        files = {
            "skills/lint/SKILL.md": "# Lint\nVersion 1.\n",
            "skills/format/SKILL.md": "# Format\nVersion 1.\n",
        }
        local_dir = self._create_local(files)
        proc = None
        try:
            proc = self._start_watch("qoder", ALL_AGENT_NAME, local_dir, repo_name)
            self._wait_cycles(2)

            # Modify one file
            (Path(local_dir) / "skills" / "lint" / "SKILL.md").write_text(
                "# Lint\nVersion 2 - updated.\n", encoding="utf-8"
            )

            self._wait_cycles(2)

            # Verify remote has updated content at the correct path
            content = self.client.download_repo_file(
                self.username, repo_name, "skills/lint/SKILL.md")
            self.assertIn("Version 2", content)

            # Other file untouched
            content2 = self.client.download_repo_file(
                self.username, repo_name, "skills/format/SKILL.md")
            self.assertIn("Version 1", content2)
        finally:
            if proc:
                self._stop_watch(proc)
            self._cleanup(local_dir)

    # -----------------------------------------------------------------------
    # 17. push_only=True: remote changes do NOT pull to local
    # -----------------------------------------------------------------------
    def test_17_push_only_ignores_remote_changes(self):
        """With push_only=True (default), remote changes should NOT be pulled."""
        repo_name = f"{AGENT_PREFIX}-push-only"
        files = {
            "AGENTS.md": "# Agents\nLocal original.\n",
            "rules/style.md": "# Style\nLocal rule.\n",
        }
        local_dir = self._create_local(files)
        proc = None
        try:
            # push_only=True is the default
            proc = self._start_watch("qoder", ALL_AGENT_NAME, local_dir, repo_name, push_only=True)
            # Wait for initial push
            self._wait_cycles(2)

            # Simulate remote change (add file + modify existing)
            remote_files = dict(files)
            remote_files["AGENTS.md"] = "# Agents\nRemote modification.\n"
            remote_files["commands/new.md"] = "# New\nAdded remotely.\n"
            self._upload_remote(repo_name, "qoder", remote_files)
            _wait(8)

            # Wait several cycles
            self._wait_cycles(3)

            # Local file should NOT be modified (push_only protects local)
            local_content = (Path(local_dir) / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Local original", local_content)
            self.assertNotIn("Remote modification", local_content)

            # Remote-only file should NOT appear locally
            new_file = Path(local_dir) / "commands" / "new.md"
            self.assertFalse(new_file.exists(), "remote-only file should NOT be pulled in push_only mode")
        finally:
            if proc:
                self._stop_watch(proc)
            self._cleanup(local_dir)

    # -----------------------------------------------------------------------
    # 18. push_only=True: remote delete does NOT delete local files
    # -----------------------------------------------------------------------
    def test_18_push_only_prevents_local_deletion(self):
        """With push_only=True, files deleted on remote should NOT be deleted locally.

        This is the key safety feature: prevents accidental data loss when
        remote state diverges (e.g. server-side reset, other client overwrites).
        """
        repo_name = f"{AGENT_PREFIX}-push-only-del"
        files = {
            "AGENTS.md": "# Agents\nKeep me safe.\n",
            "rules/important.md": "# Important\nMust not be deleted.\n",
            "agents/coder.md": "# Coder\nValuable local file.\n",
        }
        local_dir = self._create_local(files)
        proc = None
        try:
            # push_only=True (default)
            proc = self._start_watch("qoder", ALL_AGENT_NAME, local_dir, repo_name, push_only=True)
            # Wait for initial push
            self._wait_cycles(2)

            # Simulate remote catastrophe: someone overwrites remote with fewer files
            reduced_remote = {"AGENTS.md": "# Agents\nOnly this survives on remote.\n"}
            self._upload_remote(repo_name, "qoder", reduced_remote)
            _wait(8)

            # Wait for sync cycles
            self._wait_cycles(3)

            # ALL local files must still exist (push_only never deletes local)
            self.assertTrue(
                (Path(local_dir) / "rules" / "important.md").exists(),
                "push_only must protect local files from remote-side deletion"
            )
            self.assertTrue(
                (Path(local_dir) / "agents" / "coder.md").exists(),
                "push_only must protect local files from remote-side deletion"
            )
            self.assertTrue(
                (Path(local_dir) / "AGENTS.md").exists(),
                "AGENTS.md must still exist locally"
            )

            # Local content should remain unchanged
            content = (Path(local_dir) / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Keep me safe", content)
            self.assertNotIn("Only this survives", content)
        finally:
            if proc:
                self._stop_watch(proc)
            self._cleanup(local_dir)

    # -----------------------------------------------------------------------
    # 19. push_only=True: conflict scenario → local push wins (no remote pull)
    # -----------------------------------------------------------------------
    def test_19_push_only_conflict_local_wins(self):
        """With push_only=True, even when remote changed, local still pushes
        (remote never overwrites local)."""
        repo_name = f"{AGENT_PREFIX}-push-only-conflict"
        files = {
            "AGENTS.md": "# Agents\nBaseline.\n",
        }
        local_dir = self._create_local(files)
        proc = None
        try:
            proc = self._start_watch("qoder", ALL_AGENT_NAME, local_dir, repo_name, push_only=True)
            self._wait_cycles(2)

            # Stop watch
            self._stop_watch(proc)
            proc = None
            _wait(REQUEST_INTERVAL)

            # Remote changes
            self._upload_remote(repo_name, "qoder", {"AGENTS.md": "# Agents\nRemote version.\n"})
            _wait(8)

            # Local changes
            (Path(local_dir) / "AGENTS.md").write_text(
                "# Agents\nLocal version should win.\n", encoding="utf-8"
            )

            # Restart with push_only=True
            proc = self._start_watch("qoder", ALL_AGENT_NAME, local_dir, repo_name, push_only=True)
            self._wait_cycles(3)

            # Local file should retain LOCAL content (not overwritten by remote)
            local_content = (Path(local_dir) / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Local version should win", local_content)
            self.assertNotIn("Remote version", local_content)

            # Remote should eventually get the local version pushed
            remote_content = self.client.download_repo_file(self.username, repo_name, "AGENTS.md")
            self.assertIn("Local version should win", remote_content)
        finally:
            if proc:
                self._stop_watch(proc)
            self._cleanup(local_dir)


if __name__ == "__main__":
    unittest.main(verbosity=2)
