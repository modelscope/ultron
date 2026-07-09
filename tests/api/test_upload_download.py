"""Integration tests for the ``ultron upload`` and ``ultron download`` CLI commands.

Covers:
    - Upload individual sub-agent (each framework)
    - Upload all mode (qoder, nanobot, qwenpaw, openclaw)
    - Upload --dry-run (no server call)
    - Upload --list (enumerate on-disk sub-agents)
    - Upload missing --name → error
    - Upload unknown framework → error
    - Upload empty workspace → error
    - Download individual sub-agent
    - Download with --framework explicit
    - Download with --target (cross-framework conversion)
    - Download with --local_dir override
    - Download --dry-run (no write)
    - Download non-existent repo → error
    - Download unknown framework → error
    - Round-trip: upload → download → content verification
    - All-mode round-trip for file-per-agent (qoder)
    - All-mode round-trip for root-per-agent (qwenpaw)
    - Idempotent re-upload → content unchanged

Usage:
    python -m unittest tests.api.test_upload_download
    python tests/api/test_upload_download.py
"""
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from ultron.cli.client import ApiError, UltronClient
from ultron.cli.commands import cmd_download, cmd_status, cmd_upload, _repo_name
from ultron.cli import config as cli_config
from ultron.services.harness.allowlist import (
    ALL_AGENT_NAME,
    ALLOWLIST_REGISTRY,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SERVER = os.environ.get("SERVER", "http://www.modelscope.cn")
TOKEN = os.environ.get("TOKEN", "")
AGENT_PREFIX = "test-updown"

# Throttle between each test method to avoid 429 and WAF blocks
REQUEST_INTERVAL = int(os.environ.get("REQUEST_INTERVAL", "8"))


def _wait(seconds: int = 5):
    print(f"    (waiting {seconds}s...)")
    time.sleep(seconds)


def _log_429(fn, *args, **kwargs):
    """Call fn; on 429 log which API was rate-limited and re-raise."""
    try:
        return fn(*args, **kwargs)
    except ApiError as e:
        if e.status == 429:
            print(f"    [429 RATE LIMITED] {fn.__name__}()", file=sys.stderr)
        raise


# ---------------------------------------------------------------------------
# Mock file sets for testing
# ---------------------------------------------------------------------------

QODER_INDIVIDUAL_FILES = {
    "AGENTS.md": "# Agents\n\n## Available\n- reviewer\n- coder\n",
    "agents/reviewer.md": "# Reviewer\nCode review sub-agent.\n",
    "commands/review.md": "# /review\nReview code.\n",
    "rules/style.md": "# Style\nUse 4 spaces.\n",
    "skills/lint/SKILL.md": "# Lint\nRun linter.\n",
    "skills/lint/scripts/run.sh": "# lint runner\nrun flake8 on project files\n",
}

QODER_ALL_FILES = {
    "AGENTS.md": "# Agents\n\n## Available\n- reviewer\n- coder\n",
    "agents/reviewer.md": "# Reviewer\nCode review sub-agent.\n",
    "agents/coder.md": "# Coder\nCode generation sub-agent.\n",
    "commands/review.md": "# /review\nReview code.\n",
    "rules/style.md": "# Style\nUse 4 spaces.\n",
    "skills/lint/SKILL.md": "# Lint\nRun linter.\n",
}

NANOBOT_ALL_FILES = {
    "AGENTS.md": "# Agents\n",
    "SOUL.md": "# Soul\nI am nanobot.\n",
    "memory/MEMORY.md": "# Memory\n",
    "skills/search/SKILL.md": "# Search\nWeb search.\n",
}

QWENPAW_INDIVIDUAL_FILES = {
    "SOUL.md": "# Soul\nQwenPaw creative AI.\n",
    "PROFILE.md": "# Profile\nCreative writer.\n",
    "MEMORY.md": "# Memory\nStory ideas.\n",
    "skills/storytelling/SKILL.md": "# Storytelling\nNarrative skills.\n",
}

QWENPAW_ALL_FILES = {
    "bot-a/SOUL.md": "# Soul\nBot A creative AI.\n",
    "bot-a/PROFILE.md": "# Profile A\nBot A profile.\n",
    "bot-a/skills/write/SKILL.md": "# Write\nWriting skill.\n",
    "bot-b/SOUL.md": "# Soul\nBot B analysis AI.\n",
    "bot-b/PROFILE.md": "# Profile B\nBot B profile.\n",
    "bot-b/skills/analyze/SKILL.md": "# Analyze\nAnalysis skill.\n",
}

OPENCLAW_ALL_FILES = {
    "workspace/SOUL.md": "# Soul\nDefault agent.\n",
    "workspace/AGENTS.md": "# Agents\nDefault.\n",
    "workspace/skills/code/SKILL.md": "# Code\nCoding.\n",
    "workspace-helper/SOUL.md": "# Soul\nHelper agent.\n",
    "workspace-helper/AGENTS.md": "# Agents\nHelper.\n",
    "workspace-helper/skills/refactor/SKILL.md": "# Refactor\nRefactoring.\n",
}


# ===========================================================================
# Test class
# ===========================================================================

class TestUploadDownload(unittest.TestCase):
    """Integration tests for upload/download commands against a real server."""

    client: UltronClient = None  # type: ignore
    username: str = ""

    @classmethod
    def setUpClass(cls):
        cls.client = UltronClient(SERVER)
        cls.username = cls.client.login(TOKEN)
        assert cls.username, "login failed"
        print(f"    Logged in as {cls.username}")
        # Persist credentials so cmd_upload/cmd_download can resolve username
        cls._orig_data_dir = os.environ.get("ULTRON_DATA_DIR", "")
        cls._tmp_data_dir = tempfile.mkdtemp(prefix="ultron_test_cfg_")
        os.environ["ULTRON_DATA_DIR"] = cls._tmp_data_dir
        cli_config.save(SERVER, cls.username, TOKEN)

    @classmethod
    def tearDownClass(cls):
        # Restore original env
        if cls._orig_data_dir:
            os.environ["ULTRON_DATA_DIR"] = cls._orig_data_dir
        else:
            os.environ.pop("ULTRON_DATA_DIR", None)
        shutil.rmtree(cls._tmp_data_dir, ignore_errors=True)

    def setUp(self):
        time.sleep(REQUEST_INTERVAL)

    # -----------------------------------------------------------------------
    # Helper: build args namespace for cmd_upload / cmd_download
    # -----------------------------------------------------------------------
    def _upload_args(self, framework, name, local_dir=None, dry_run=False, repo=None):
        return SimpleNamespace(
            framework=framework,
            name=name,
            repo=repo,
            local_dir=local_dir,
            server=SERVER,
            token=TOKEN,
            message=None,
            dry_run=dry_run,
        )

    def _download_args(self, name, framework=None, target=None, local_dir=None, dry_run=False, repo=None):
        return SimpleNamespace(
            name=name,
            repo=repo or _repo_name(framework or "", name or ""),
            framework=framework,
            target=target,
            local_dir=local_dir,
            server=SERVER,
            token=TOKEN,
            dry_run=dry_run,
        )

    def _create_local_workspace(self, files: dict) -> str:
        """Write files into a temp dir and return its path."""
        tmpdir = tempfile.mkdtemp(prefix="ultron_test_")
        for rel, content in files.items():
            fp = Path(tmpdir) / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                fp.write_bytes(content)
            else:
                fp.write_text(content, encoding="utf-8")
        return tmpdir

    def _cleanup_dir(self, path: str):
        if path and Path(path).exists():
            shutil.rmtree(path, ignore_errors=True)

    # -----------------------------------------------------------------------
    # 01. Upload: basic individual sub-agent
    # -----------------------------------------------------------------------
    def test_01_upload_individual_qoder(self):
        """Upload a single qoder sub-agent via --local_dir."""
        # agent_name must match the agents/{name}.md file
        agent_name = f"{AGENT_PREFIX}-qoder-ind"
        files = {
            "AGENTS.md": "# Agents\n\n## Available\n- reviewer\n",
            f"agents/{agent_name}.md": "# Test Agent\nIntegration test.\n",
            "commands/review.md": "# /review\nReview code.\n",
            "rules/style.md": "# Style\nUse 4 spaces.\n",
            "skills/lint/SKILL.md": "# Lint\nRun linter.\n",
            "skills/lint/scripts/run.sh": "# lint runner\nrun flake8 on project files\n",
        }
        local = self._create_local_workspace(files)
        try:
            args = self._upload_args("qoder", agent_name, local_dir=local)
            rc = cmd_upload(args)
            self.assertEqual(rc, 0, "upload should succeed")
        finally:
            self._cleanup_dir(local)

    # -----------------------------------------------------------------------
    # 02. Upload: --name all for file-per-agent (qoder)
    # -----------------------------------------------------------------------
    def test_02_upload_all_qoder(self):
        """Upload all qoder sub-agents at once (agents/*.md wildcard)."""
        local = self._create_local_workspace(QODER_ALL_FILES)
        try:
            args = self._upload_args("qoder", ALL_AGENT_NAME, local_dir=local)
            rc = cmd_upload(args)
            self.assertEqual(rc, 0, "upload all should succeed")
        finally:
            self._cleanup_dir(local)

    # -----------------------------------------------------------------------
    # 03. Upload: --name all for root-per-agent (qwenpaw)
    # -----------------------------------------------------------------------
    def test_03_upload_all_qwenpaw(self):
        """Upload all qwenpaw sub-agents (paths prefixed with agent dir)."""
        local = self._create_local_workspace(QWENPAW_ALL_FILES)
        try:
            args = self._upload_args("qwenpaw", ALL_AGENT_NAME, local_dir=local)
            rc = cmd_upload(args)
            self.assertEqual(rc, 0, "upload all qwenpaw should succeed")
        finally:
            self._cleanup_dir(local)

    # -----------------------------------------------------------------------
    # 04. Upload: --name all for openclaw (workspace* prefix)
    # -----------------------------------------------------------------------
    def test_04_upload_all_openclaw(self):
        """Upload all openclaw agents (workspace/ + workspace-*)."""
        local = self._create_local_workspace(OPENCLAW_ALL_FILES)
        try:
            args = self._upload_args("openclaw", ALL_AGENT_NAME, local_dir=local)
            rc = cmd_upload(args)
            self.assertEqual(rc, 0, "upload all openclaw should succeed")
        finally:
            self._cleanup_dir(local)

    # -----------------------------------------------------------------------
    # 05. Upload: --dry-run
    # -----------------------------------------------------------------------
    def test_05_upload_dry_run(self):
        """--dry-run should return 0 without making server calls."""
        local = self._create_local_workspace(QODER_INDIVIDUAL_FILES)
        try:
            args = self._upload_args("qoder", "dry-run-test", local_dir=local, dry_run=True)
            rc = cmd_upload(args)
            self.assertEqual(rc, 0)
        finally:
            self._cleanup_dir(local)

    # -----------------------------------------------------------------------
    # 06. List: list sub-agents
    # -----------------------------------------------------------------------
    def test_06_upload_list(self):
        """cmd_status should enumerate sub-agents on disk and return 0."""
        local = self._create_local_workspace(QODER_ALL_FILES)
        try:
            args = SimpleNamespace(framework="qoder", local_dir=local)
            rc = cmd_status(args)
            self.assertEqual(rc, 0)
        finally:
            self._cleanup_dir(local)

    # -----------------------------------------------------------------------
    # 07. Upload: missing --name with multiple agents → error
    # -----------------------------------------------------------------------
    def test_07_upload_missing_name(self):
        """Upload without --name when multiple agents exist should fail."""
        local = self._create_local_workspace(QODER_ALL_FILES)
        try:
            args = self._upload_args("qoder", None, local_dir=local)
            rc = cmd_upload(args)
            self.assertEqual(rc, 1)
        finally:
            self._cleanup_dir(local)

    # -----------------------------------------------------------------------
    # 08. Upload: unknown framework → error
    # -----------------------------------------------------------------------
    def test_08_upload_unknown_framework(self):
        """Upload with an unregistered framework should fail."""
        local = self._create_local_workspace({"SOUL.md": "# test\n"})
        try:
            args = self._upload_args("nonexistent-fw", "test", local_dir=local)
            rc = cmd_upload(args)
            self.assertEqual(rc, 1)
        finally:
            self._cleanup_dir(local)

    # -----------------------------------------------------------------------
    # 09. Upload: empty workspace → error
    # -----------------------------------------------------------------------
    def test_09_upload_empty_workspace(self):
        """Upload from an empty dir should fail (no files match patterns)."""
        local = tempfile.mkdtemp(prefix="ultron_test_empty_")
        try:
            args = self._upload_args("qoder", "empty-test", local_dir=local)
            rc = cmd_upload(args)
            self.assertEqual(rc, 1)
        finally:
            self._cleanup_dir(local)

    # -----------------------------------------------------------------------
    # 10. Upload: nanobot all mode (single-agent -> full workspace)
    # -----------------------------------------------------------------------
    def test_10_upload_all_nanobot(self):
        """Upload the whole nanobot workspace in all mode."""
        local = self._create_local_workspace(NANOBOT_ALL_FILES)
        try:
            args = self._upload_args("nanobot", ALL_AGENT_NAME, local_dir=local)
            rc = cmd_upload(args)
            self.assertEqual(rc, 0, "upload all nanobot should succeed")
        finally:
            self._cleanup_dir(local)

    # -----------------------------------------------------------------------
    # 11. Download: existing repo
    # -----------------------------------------------------------------------
    def test_11_download_existing_repo(self):
        """Download a previously uploaded repo into a temp dir."""
        # Ensure repo exists from test_01
        agent_name = f"{AGENT_PREFIX}-qoder-ind"
        _wait(5)  # WAF cooldown between download-heavy tests
        local = tempfile.mkdtemp(prefix="ultron_test_dl_")
        try:
            args = self._download_args(agent_name, framework="qoder", local_dir=local)
            rc = cmd_download(args)
            self.assertEqual(rc, 0, "download should succeed")
            # Verify at least one file was written
            written = list(Path(local).rglob("*"))
            files = [f for f in written if f.is_file()]
            self.assertGreater(len(files), 0, "should have downloaded files")
        finally:
            self._cleanup_dir(local)

    # -----------------------------------------------------------------------
    # 12. Download: --dry-run
    # -----------------------------------------------------------------------
    def test_12_download_dry_run(self):
        """--dry-run should show files without writing."""
        agent_name = f"{AGENT_PREFIX}-qoder-ind"
        _wait(5)  # WAF cooldown between download-heavy tests
        local = tempfile.mkdtemp(prefix="ultron_test_dldry_")
        try:
            args = self._download_args(agent_name, framework="qoder", local_dir=local, dry_run=True)
            rc = cmd_download(args)
            self.assertEqual(rc, 0)
            # Verify nothing was written
            files = [f for f in Path(local).rglob("*") if f.is_file()]
            self.assertEqual(len(files), 0, "dry-run should not write files")
        finally:
            self._cleanup_dir(local)

    # -----------------------------------------------------------------------
    # 13. Download: non-existent repo → error
    # -----------------------------------------------------------------------
    def test_13_download_nonexistent_repo(self):
        """Download a repo that doesn't exist should fail."""
        local = tempfile.mkdtemp(prefix="ultron_test_dlne_")
        try:
            args = self._download_args("nonexistent-repo-xyz-99999", framework="qoder", local_dir=local)
            rc = cmd_download(args)
            self.assertEqual(rc, 1)
        finally:
            self._cleanup_dir(local)

    # -----------------------------------------------------------------------
    # 14. Download: unknown target framework → error
    # -----------------------------------------------------------------------
    def test_14_download_unknown_target(self):
        """Download with --target pointing to unknown framework should fail."""
        agent_name = f"{AGENT_PREFIX}-qoder-ind"
        local = tempfile.mkdtemp(prefix="ultron_test_dluf_")
        try:
            args = self._download_args(agent_name, framework="qoder", target="badfw", local_dir=local)
            rc = cmd_download(args)
            self.assertEqual(rc, 1)
        finally:
            self._cleanup_dir(local)

    # -----------------------------------------------------------------------
    # 15. Download: cross-framework conversion
    # -----------------------------------------------------------------------
    def test_15_download_cross_framework(self):
        """Download with --target converts files to target format."""
        # Upload nanobot files first
        agent_name = f"{AGENT_PREFIX}-nanobot-conv"
        nanobot_files = {
            "SOUL.md": "# Soul\nConversion test.\n",
            "AGENTS.md": "# Agents\nNanobot agents.\n",
            "skills/search/SKILL.md": "# Search\nSearch skill.\n",
        }
        local_up = self._create_local_workspace(nanobot_files)
        try:
            args = self._upload_args("nanobot", agent_name, local_dir=local_up)
            rc = cmd_upload(args)
            self.assertEqual(rc, 0)
        finally:
            self._cleanup_dir(local_up)

        _wait(5)

        # Download as openclaw format
        local_dl = tempfile.mkdtemp(prefix="ultron_test_dlconv_")
        try:
            args = self._download_args(agent_name, framework="nanobot", target="openclaw", local_dir=local_dl)
            rc = cmd_download(args)
            self.assertEqual(rc, 0)
            # Verify files exist
            files = [f for f in Path(local_dl).rglob("*") if f.is_file()]
            self.assertGreater(len(files), 0)
        finally:
            self._cleanup_dir(local_dl)

    # -----------------------------------------------------------------------
    # 16. Round-trip: upload → list → download → verify content
    # -----------------------------------------------------------------------
    def test_16_roundtrip_content_verify(self):
        """Upload files, then download and verify content matches."""
        agent_name = f"{AGENT_PREFIX}-roundtrip"
        files = {
            "AGENTS.md": "# Roundtrip Agents\nTest content.\n",
            f"agents/{agent_name}.md": "# test-rt\nRoundtrip sub-agent.\n",
            "rules/naming.md": "# Naming\nUse snake_case.\n",
            "skills/format/SKILL.md": "# Format\nCode formatter.\n",
        }
        local_up = self._create_local_workspace(files)
        try:
            args = self._upload_args("qoder", agent_name, local_dir=local_up)
            rc = cmd_upload(args)
            self.assertEqual(rc, 0)
        finally:
            self._cleanup_dir(local_up)

        _wait(5)

        # Verify via client API
        server_files = self.client.list_repo_files(self.username, _repo_name("qoder", agent_name))
        uploaded_keys = set(files.keys())
        server_set = set(server_files)
        missing = uploaded_keys - server_set
        self.assertFalse(missing, f"files missing on server: {missing}")

        # Download and verify content
        for rel, expected in files.items():
            if rel in server_set:
                actual = self.client.download_repo_file(self.username, _repo_name("qoder", agent_name), rel)
                self.assertEqual(actual.strip(), expected.strip(),
                                 f"content mismatch for {rel}")

    # -----------------------------------------------------------------------
    # 17. Round-trip: all-mode qoder
    # -----------------------------------------------------------------------
    def test_17_roundtrip_all_qoder(self):
        """Upload qoder all → download → verify multiple agents collected."""
        local_up = self._create_local_workspace(QODER_ALL_FILES)
        try:
            args = self._upload_args("qoder", ALL_AGENT_NAME, local_dir=local_up)
            rc = cmd_upload(args)
            self.assertEqual(rc, 0)
        finally:
            self._cleanup_dir(local_up)

        _wait(5)

        repo = _repo_name("qoder", ALL_AGENT_NAME)
        server_files = self.client.list_repo_files(self.username, repo)
        server_set = set(server_files)
        # Both agents/reviewer.md and agents/coder.md should be uploaded
        self.assertIn("agents/reviewer.md", server_set)
        self.assertIn("agents/coder.md", server_set)
        self.assertIn("AGENTS.md", server_set)

    # -----------------------------------------------------------------------
    # 18. Round-trip: all-mode qwenpaw (root-per-agent with prefix)
    # -----------------------------------------------------------------------
    def test_18_roundtrip_all_qwenpaw(self):
        """Upload qwenpaw all → verify agent-prefixed paths on server."""
        local_up = self._create_local_workspace(QWENPAW_ALL_FILES)
        try:
            args = self._upload_args("qwenpaw", ALL_AGENT_NAME, local_dir=local_up)
            rc = cmd_upload(args)
            self.assertEqual(rc, 0)
        finally:
            self._cleanup_dir(local_up)

        _wait(5)

        repo = _repo_name("qwenpaw", ALL_AGENT_NAME)
        server_files = self.client.list_repo_files(self.username, repo)
        server_set = set(server_files)
        # Files should be prefixed with bot-a/ and bot-b/
        self.assertIn("bot-a/SOUL.md", server_set)
        self.assertIn("bot-b/SOUL.md", server_set)
        self.assertIn("bot-a/skills/write/SKILL.md", server_set)

    # -----------------------------------------------------------------------
    # 19. Round-trip: all-mode openclaw (workspace* prefix)
    # -----------------------------------------------------------------------
    def test_19_roundtrip_all_openclaw(self):
        """Upload openclaw all → verify workspace-prefixed paths."""
        local_up = self._create_local_workspace(OPENCLAW_ALL_FILES)
        try:
            args = self._upload_args("openclaw", ALL_AGENT_NAME, local_dir=local_up)
            rc = cmd_upload(args)
            self.assertEqual(rc, 0)
        finally:
            self._cleanup_dir(local_up)

        _wait(5)

        repo = _repo_name("openclaw", ALL_AGENT_NAME)
        server_files = self.client.list_repo_files(self.username, repo)
        server_set = set(server_files)
        self.assertIn("workspace/SOUL.md", server_set)
        self.assertIn("workspace-helper/SOUL.md", server_set)

    # -----------------------------------------------------------------------
    # 20. Idempotent re-upload
    # -----------------------------------------------------------------------
    def test_20_idempotent_reupload(self):
        """Re-uploading same content should succeed without errors."""
        agent_name = f"{AGENT_PREFIX}-idempotent"
        files = {"AGENTS.md": "# Agents\nIdempotent test.\n", f"agents/{agent_name}.md": "# Test\n"}
        local = self._create_local_workspace(files)
        try:
            for _ in range(2):
                args = self._upload_args("qoder", agent_name, local_dir=local)
                rc = cmd_upload(args)
                self.assertEqual(rc, 0)
                _wait(REQUEST_INTERVAL)
        finally:
            self._cleanup_dir(local)

    # -----------------------------------------------------------------------
    # 21. Upload then modify → re-upload → verify new content
    # -----------------------------------------------------------------------
    def test_21_upload_modify_reupload(self):
        """Modify workspace and re-upload; server should have new content."""
        agent_name = f"{AGENT_PREFIX}-modify"
        files_v1 = {"AGENTS.md": "# V1\nOriginal.\n", f"agents/{agent_name}.md": "# Agent V1\n"}
        files_v2 = {"AGENTS.md": "# V2\nModified.\n", f"agents/{agent_name}.md": "# Agent V1 updated\n"}

        # Upload V1
        local = self._create_local_workspace(files_v1)
        try:
            rc = cmd_upload(self._upload_args("qoder", agent_name, local_dir=local))
            self.assertEqual(rc, 0)
        finally:
            self._cleanup_dir(local)

        _wait(5)

        # Upload V2
        local = self._create_local_workspace(files_v2)
        try:
            rc = cmd_upload(self._upload_args("qoder", agent_name, local_dir=local))
            self.assertEqual(rc, 0)
        finally:
            self._cleanup_dir(local)

        _wait(5)

        # Verify V2 content
        content = self.client.download_repo_file(self.username, _repo_name("qoder", agent_name), "AGENTS.md")
        self.assertIn("V2", content)
        self.assertIn("Modified", content)

    # -----------------------------------------------------------------------
    # 22. Download with --local_dir override
    # -----------------------------------------------------------------------
    def test_22_download_local_dir_override(self):
        """Download writes to the specified --local_dir, not default path."""
        agent_name = f"{AGENT_PREFIX}-qoder-ind"
        custom_dir = tempfile.mkdtemp(prefix="ultron_test_custom_")
        try:
            args = self._download_args(agent_name, framework="qoder", local_dir=custom_dir)
            rc = cmd_download(args)
            self.assertEqual(rc, 0)
            files = [f for f in Path(custom_dir).rglob("*") if f.is_file()]
            self.assertGreater(len(files), 0)
            # Files should be under custom_dir
            for f in files:
                self.assertTrue(str(f).startswith(custom_dir))
        finally:
            self._cleanup_dir(custom_dir)

    # -----------------------------------------------------------------------
    # 23. Upload: all frameworks individually
    # -----------------------------------------------------------------------
    def test_23_upload_each_framework(self):
        """Upload a minimal file set for each registered framework."""
        for fw in ALLOWLIST_REGISTRY:
            with self.subTest(framework=fw):
                agent_name = f"{AGENT_PREFIX}-fw-{fw}"
                # Build files that match the framework's patterns with this agent_name
                if fw == "qoder":
                    files = {"AGENTS.md": "# Agents\n", f"agents/{agent_name}.md": "# X\n"}
                elif fw == "nanobot":
                    files = {"SOUL.md": "# Soul\n"}
                elif fw == "openclaw":
                    files = {"SOUL.md": "# Soul\n", "IDENTITY.md": "# ID\n"}
                elif fw == "qwenpaw":
                    files = {"SOUL.md": "# Soul\n", "PROFILE.md": "# P\n"}
                elif fw == "hermes":
                    files = {"SOUL.md": "# Soul\n"}
                elif fw == "openhuman":
                    files = {"wiki/identity.md": "# Identity\n"}
                elif fw == "ms-agent":
                    files = {"profile.md": "# Profile\n", "MEMORY.md": "# Memory\n"}
                else:
                    files = {"SOUL.md": "# Soul\n"}
                local = self._create_local_workspace(files)
                try:
                    args = self._upload_args(fw, agent_name, local_dir=local)
                    rc = cmd_upload(args)
                    self.assertEqual(rc, 0, f"upload failed for {fw}")
                finally:
                    self._cleanup_dir(local)
                _wait(REQUEST_INTERVAL)

    # -----------------------------------------------------------------------
    # 24. Upload: qoder individual (only reviewer, not coder)
    # -----------------------------------------------------------------------
    def test_24_upload_individual_filters_agent(self):
        """Upload qoder with --name reviewer should NOT include agents/coder.md."""
        files = {
            "AGENTS.md": "# Agents\n",
            "agents/reviewer.md": "# Reviewer\n",
            "agents/coder.md": "# Coder\n",
            "rules/style.md": "# Style\n",
        }
        agent_name = f"{AGENT_PREFIX}-filter"
        local = self._create_local_workspace(files)
        try:
            # Use allowlist directly to verify filtering
            spec = ALLOWLIST_REGISTRY["qoder"](agent_name="reviewer", local_dir=Path(local))
            collected = spec.collect()
            self.assertIn("agents/reviewer.md", collected)
            self.assertNotIn("agents/coder.md", collected,
                             "individual mode should not include other agents")
            self.assertIn("rules/style.md", collected, "shared files should be included")
        finally:
            self._cleanup_dir(local)

    # -----------------------------------------------------------------------
    # 25. Upload: qoder all mode collects all agents
    # -----------------------------------------------------------------------
    def test_25_upload_all_collects_everything(self):
        """Upload qoder --name all should include ALL agents/*.md files."""
        files = {
            "AGENTS.md": "# Agents\n",
            "agents/reviewer.md": "# Reviewer\n",
            "agents/coder.md": "# Coder\n",
            "agents/tester.md": "# Tester\n",
            "rules/style.md": "# Style\n",
        }
        local = self._create_local_workspace(files)
        try:
            spec = ALLOWLIST_REGISTRY["qoder"](agent_name=ALL_AGENT_NAME, local_dir=Path(local))
            collected = spec.collect()
            self.assertIn("agents/reviewer.md", collected)
            self.assertIn("agents/coder.md", collected)
            self.assertIn("agents/tester.md", collected)
            self.assertIn("rules/style.md", collected)
            self.assertIn("AGENTS.md", collected)
        finally:
            self._cleanup_dir(local)

    # -----------------------------------------------------------------------
    # 26. qwenpaw all: workspace_root lifted, patterns prefixed
    # -----------------------------------------------------------------------
    def test_26_qwenpaw_all_collect_prefixed(self):
        """qwenpaw all mode collects from multiple sub-agent dirs with prefix."""
        local = self._create_local_workspace(QWENPAW_ALL_FILES)
        try:
            spec = ALLOWLIST_REGISTRY["qwenpaw"](agent_name=ALL_AGENT_NAME, local_dir=Path(local))
            collected = spec.collect()
            self.assertIn("bot-a/SOUL.md", collected)
            self.assertIn("bot-b/SOUL.md", collected)
            self.assertIn("bot-a/skills/write/SKILL.md", collected)
            self.assertIn("bot-b/skills/analyze/SKILL.md", collected)
        finally:
            self._cleanup_dir(local)

    # -----------------------------------------------------------------------
    # 27. openclaw all: workspace* prefix matches both dirs
    # -----------------------------------------------------------------------
    def test_27_openclaw_all_collect_workspace_prefix(self):
        """openclaw all mode collects workspace/ and workspace-*/ directories."""
        local = self._create_local_workspace(OPENCLAW_ALL_FILES)
        try:
            spec = ALLOWLIST_REGISTRY["openclaw"](agent_name=ALL_AGENT_NAME, local_dir=Path(local))
            collected = spec.collect()
            self.assertIn("workspace/SOUL.md", collected)
            self.assertIn("workspace-helper/SOUL.md", collected)
            self.assertIn("workspace/skills/code/SKILL.md", collected)
            self.assertIn("workspace-helper/skills/refactor/SKILL.md", collected)
        finally:
            self._cleanup_dir(local)

    # -----------------------------------------------------------------------
    # 28. openclaw all: non-workspace dirs excluded
    # -----------------------------------------------------------------------
    def test_28_openclaw_all_excludes_non_workspace(self):
        """openclaw all should NOT collect files outside workspace* dirs."""
        files = dict(OPENCLAW_ALL_FILES)
        files["config/settings.json"] = '{"key": "value"}'
        files["logs/app.log"] = "log line\n"
        local = self._create_local_workspace(files)
        try:
            spec = ALLOWLIST_REGISTRY["openclaw"](agent_name=ALL_AGENT_NAME, local_dir=Path(local))
            collected = spec.collect()
            self.assertNotIn("config/settings.json", collected)
            self.assertNotIn("logs/app.log", collected)
        finally:
            self._cleanup_dir(local)

    # -----------------------------------------------------------------------
    # 29. Download: all-mode round-trip (download to local_dir, verify)
    # -----------------------------------------------------------------------
    def test_29_download_all_roundtrip(self):
        """Upload qoder all → download → verify files land correctly."""
        # Upload first to ensure repo has qoder-all content
        local_up = self._create_local_workspace(QODER_ALL_FILES)
        try:
            args = self._upload_args("qoder", ALL_AGENT_NAME, local_dir=local_up)
            rc = cmd_upload(args)
            self.assertEqual(rc, 0)
        finally:
            self._cleanup_dir(local_up)

        _wait(5)

        local_dl = tempfile.mkdtemp(prefix="ultron_test_dlall_")
        try:
            args = self._download_args(ALL_AGENT_NAME, framework="qoder", local_dir=local_dl)
            rc = cmd_download(args)
            self.assertEqual(rc, 0)
            # Should have both agent files
            dl_files = {
                str(f.relative_to(local_dl))
                for f in Path(local_dl).rglob("*") if f.is_file()
            }
            self.assertIn("agents/reviewer.md", dl_files)
            self.assertIn("agents/coder.md", dl_files)
        finally:
            self._cleanup_dir(local_dl)

    # -----------------------------------------------------------------------
    # 30. supports_individual_watch property check
    # -----------------------------------------------------------------------
    def test_30_supports_individual_watch(self):
        """Only file-per-agent + shared frameworks (qoder) disallow individual watch."""
        qoder = ALLOWLIST_REGISTRY["qoder"](agent_name="reviewer")
        nanobot = ALLOWLIST_REGISTRY["nanobot"](agent_name="helper")
        qwenpaw = ALLOWLIST_REGISTRY["qwenpaw"](agent_name="bot-a")
        openclaw = ALLOWLIST_REGISTRY["openclaw"](agent_name="helper")
        hermes = ALLOWLIST_REGISTRY["hermes"](agent_name="default")
        ms_agent = ALLOWLIST_REGISTRY["ms-agent"](agent_name="default")

        # file-per-agent + shared: shared files cascade, individual watch unsupported
        self.assertFalse(qoder.supports_individual_watch)
        # single-agent installs: the whole workspace is the one agent
        self.assertTrue(nanobot.supports_individual_watch)
        self.assertTrue(hermes.supports_individual_watch)
        self.assertTrue(ms_agent.supports_individual_watch)
        # root-per-agent: each agent is its own directory
        self.assertTrue(qwenpaw.supports_individual_watch)
        self.assertTrue(openclaw.supports_individual_watch)


if __name__ == "__main__":
    unittest.main(verbosity=2)
