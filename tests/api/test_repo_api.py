# Copyright (c) ModelScope Contributors. All rights reserved.
"""Contract tests for the repository API (/api/v1/agents/*).

These call the route handlers in ``ultron.api.routers.repo`` directly (they are
async functions) against a patched ``server_state.ultron``. This avoids booting
the full FastAPI app — which instantiates a real embedding service that needs
network access — while still exercising all adapter logic, status codes, and
base64/LFS handling.
"""

import asyncio
import base64
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from ultron.api.routers import repo
from ultron.api.schemas import CommitAction, CommitRequest, CreateRepoRequest, LfsBatchRequest


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _run(coro):
    return asyncio.run(coro)


class TestRepoApi(unittest.TestCase):
    def setUp(self):
        import ultron.server_state as st

        self._store = {}

        def _get_profile(user_id, agent_id):
            return self._store.get((user_id, agent_id))

        def _sync_up(user_id, agent_id, product, resources):
            key = (user_id, agent_id)
            rev = (self._store.get(key, {}).get("revision", 0)) + 1
            self._store[key] = {
                "user_id": user_id, "agent_id": agent_id, "product": product,
                "resources": dict(resources), "revision": rev, "updated_at": 123,
            }
            return {"revision": rev}

        self.mock = MagicMock()
        self.mock.get_harness_profile.side_effect = _get_profile
        self.mock.harness_sync_up.side_effect = _sync_up
        self.patcher = patch.object(st, "ultron", self.mock)
        self.patcher.start()
        self.user = {"username": "alice"}

    def tearDown(self):
        self.patcher.stop()

    def test_full_roundtrip(self):
        # 1. create
        r = _run(repo.create_repo(
            CreateRepoRequest(Path="alice", Name="myagent", Framework="QwenPaw"),
            self.user,
        ))
        self.assertEqual(r["data"]["Framework"], "QwenPaw")

        # 2. check exists
        r = _run(repo.check_repo("alice", "myagent", self.user))
        self.assertEqual(r["data"]["Framework"], "QwenPaw")

        # 3. commit a normal text file
        r = _run(repo.commit_repo("alice", "myagent", "master", CommitRequest(
            commit_message="add soul",
            actions=[CommitAction(action="update", path="SOUL.md", type="normal",
                                  size=5, sha256="", content=_b64("hello"), encoding="base64")],
        ), self.user))
        self.assertEqual(r["data"]["files"], 1)

        # 4. list files
        r = _run(repo.list_repo_files("alice", "myagent", "", "true", "", 1, 100, self.user))
        self.assertEqual([f["Path"] for f in r["data"]["Files"]], ["SOUL.md"])

        # 5. download — round-trips
        r = _run(repo.get_repo_file("alice", "myagent", "SOUL.md", "", self.user))
        self.assertEqual(base64.b64decode(r["data"]["Content"]).decode("utf-8"), "hello")

    def test_check_missing_repo_404(self):
        with self.assertRaises(HTTPException) as ctx:
            _run(repo.check_repo("alice", "nope", self.user))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_create_duplicate_409(self):
        req = CreateRepoRequest(Path="alice", Name="dup", Framework="OpenClaw")
        _run(repo.create_repo(req, self.user))
        with self.assertRaises(HTTPException) as ctx:
            _run(repo.create_repo(req, self.user))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_path_owner_mismatch_403(self):
        with self.assertRaises(HTTPException) as ctx:
            _run(repo.check_repo("bob", "x", self.user))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_lfs_batch_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            _run(repo.lfs_batch("alice", "a", LfsBatchRequest(
                operation="upload", objects=[{"oid": "abc", "size": 9}]), self.user))
        self.assertEqual(ctx.exception.status_code, 501)

    def test_lfs_action_rejected(self):
        _run(repo.create_repo(CreateRepoRequest(
            Path="alice", Name="a2", Framework="QwenPaw"), self.user))
        with self.assertRaises(HTTPException) as ctx:
            _run(repo.commit_repo("alice", "a2", "master", CommitRequest(
                commit_message="big",
                actions=[CommitAction(action="update", path="data.bin", type="lfs",
                                      size=999, sha256="abc", content="", encoding="")],
            ), self.user))
        self.assertEqual(ctx.exception.status_code, 501)

    def test_invalid_base64_rejected(self):
        _run(repo.create_repo(CreateRepoRequest(
            Path="alice", Name="a4", Framework="QwenPaw"), self.user))
        with self.assertRaises(HTTPException) as ctx:
            _run(repo.commit_repo("alice", "a4", "master", CommitRequest(
                commit_message="bad",
                actions=[CommitAction(action="update", path="X.md", type="normal",
                                      size=1, sha256="", content="!!!notbase64!!!", encoding="base64")],
            ), self.user))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_delete_action(self):
        _run(repo.create_repo(CreateRepoRequest(
            Path="alice", Name="a3", Framework="QwenPaw"), self.user))
        _run(repo.commit_repo("alice", "a3", "master", CommitRequest(
            commit_message="add",
            actions=[CommitAction(action="update", path="X.md", type="normal",
                                  size=1, sha256="", content=_b64("x"), encoding="base64")],
        ), self.user))
        r = _run(repo.commit_repo("alice", "a3", "master", CommitRequest(
            commit_message="del",
            actions=[CommitAction(action="delete", path="X.md", type="normal",
                                  size=0, sha256="", content="", encoding="")],
        ), self.user))
        self.assertEqual(r["data"]["files"], 0)

    def test_list_files_non_recursive_and_root(self):
        _run(repo.create_repo(CreateRepoRequest(
            Path="alice", Name="a5", Framework="QwenPaw"), self.user))
        _run(repo.commit_repo("alice", "a5", "master", CommitRequest(
            commit_message="tree",
            actions=[
                CommitAction(action="update", path="SOUL.md", type="normal", size=1,
                             sha256="", content=_b64("s"), encoding="base64"),
                CommitAction(action="update", path="memory/a.md", type="normal", size=1,
                             sha256="", content=_b64("a"), encoding="base64"),
            ],
        ), self.user))
        # non-recursive at root: only top-level SOUL.md
        r = _run(repo.list_repo_files("alice", "a5", "", "false", "", 1, 100, self.user))
        self.assertEqual([f["Path"] for f in r["data"]["Files"]], ["SOUL.md"])
        # Root=memory: only the memory file
        r = _run(repo.list_repo_files("alice", "a5", "", "true", "memory", 1, 100, self.user))
        self.assertEqual([f["Path"] for f in r["data"]["Files"]], ["memory/a.md"])


if __name__ == "__main__":
    unittest.main()
