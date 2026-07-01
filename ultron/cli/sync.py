# Copyright (c) ModelScope Contributors. All rights reserved.
"""Core sync logic: backup, zip, bidirectional sync helpers."""
import base64
import hashlib
import io
import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Union

from .cache import cache_dir

if TYPE_CHECKING:
    from .client import RemoteFileInfo, UltronClient

logger = logging.getLogger("ultron.watch")



def zip_resources(resources: Dict[str, Union[str, bytes]], wrapper: str = "agent") -> bytes:
    """Pack resources into a deterministic in-memory zip.

    The server always strips the first directory level from zip entries, so we
    wrap all files under a top-level folder (``wrapper/``). This ensures that
    after stripping, the remaining path matches the original ``rel_path``.

    Args:
        resources: A dict {rel_path: content}. Values are written directly
                   via ``ZipFile.writestr`` (accepts both str and bytes).
        wrapper: Name of the top-level wrapper directory (default: "agent").
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, value in sorted(resources.items()):
            zf.writestr(f"{wrapper}/{rel}", value)
    return buf.getvalue()


def backup_local(spec, name: str) -> Path:
    """Zip all local agent files into a timestamped backup in the cache dir.

    Returns the path to the created zip file.
    """
    resources: Dict[str, bytes] = spec.collect_bytes()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = cache_dir() / f"{name}_{timestamp}.zip"
    zip_path.write_bytes(zip_resources(resources))
    return zip_path



# ---- Bidirectional sync helpers ----

def sha256_content(content: Union[str, bytes]) -> str:
    """Compute sha256 of content (accepts str or bytes)."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def detect_local_changes(
    local_resources: Dict[str, bytes],
    baseline_sha256: Dict[str, str],
) -> Dict[str, bytes]:
    """Compare local files against the sync baseline sha256 map.

    Returns a dict of files that differ:
      - key present with non-empty value: content changed or file is new locally
      - key present with empty bytes value: file was deleted locally (in baseline but not local)
    """
    changed: Dict[str, bytes] = {}
    # Modified or new files.
    for rel, content in local_resources.items():
        local_sha = sha256_content(content)
        if baseline_sha256.get(rel) != local_sha:
            changed[rel] = content
    # Deleted files (in baseline but not in local).
    for rel in baseline_sha256:
        if rel not in local_resources:
            changed[rel] = b""
    return changed


def push_resources(
    client: "UltronClient",
    username: str,
    name: str,
    framework: str,
    resources: Dict[str, bytes],
) -> None:
    """Full upload via two-step OSS, then create/update agent repo.

    Raises on failure (caller should NOT update baseline on exception).
    Does nothing if *resources* is empty.
    """
    if not resources:
        logger.warning("push_resources called with empty resources; skipping.")
        return
    gid = client.upload_file(resources)
    if not gid:
        logger.warning("upload_file returned empty gid; skipping create_repo.")
        return
    client.create_repo(username, name, framework, system_prompt_files=gid)
    logger.info("Pushed %d file(s) via OSS (gid=%s).", len(resources), gid)


def push_incremental(
    client: "UltronClient",
    username: str,
    name: str,
    changed: Dict[str, bytes],
    remote_paths: set,
) -> None:
    """Incremental push via commit interface.

    Builds create/update/delete actions and commits in one request.
    Raises on failure (caller should NOT update baseline on exception).
    """
    actions: List[dict] = []
    for fpath, content in changed.items():
        if not content:  # empty bytes = delete
            actions.append({"action": "delete", "file_path": fpath})
        else:
            action_type = "update" if fpath in remote_paths else "create"
            # Try UTF-8 decode; fall back to base64 for binary.
            try:
                text = content.decode("utf-8")
                actions.append({"action": action_type, "file_path": fpath,
                                "content": text, "encoding": "text"})
            except UnicodeDecodeError:
                b64 = base64.b64encode(content).decode("ascii")
                actions.append({"action": action_type, "file_path": fpath,
                                "content": b64, "encoding": "base64"})
    if actions:
        client.commit_files(username, name, actions, commit_message="watch sync")
        logger.info("Committed %d action(s) incrementally.", len(actions))


def pull_incremental(
    client: "UltronClient",
    username: str,
    name: str,
    spec,
    remote_files: "List[RemoteFileInfo]",
    local_resources: Dict[str, bytes],
) -> int:
    """Incrementally pull remote changes to local workspace.

    Compares remote sha256 with local content sha256:
      - remote has file & sha256 differs (or local missing) → download & write
      - local has file & remote doesn't → delete local

    Returns the number of files changed. Raises if any download fails
    (caller should NOT update baseline on exception).
    """
    root: Path = spec.workspace_root
    resolved_root = root.resolve()
    remote_sha_map = {f.path: f.sha256 for f in remote_files}
    remote_paths = set(remote_sha_map.keys())
    local_paths = set(local_resources.keys())
    changes = 0

    # Download files that are new or changed on remote.
    for rfile in remote_files:
        target = (root / rfile.path).resolve()
        if not target.is_relative_to(resolved_root):
            logger.warning("  Skipped (path traversal): %s", rfile.path)
            continue
        local_content = local_resources.get(rfile.path)
        if local_content is not None:
            local_sha = sha256_content(local_content)
            if local_sha == rfile.sha256:
                continue  # identical, skip
        # Need to download.
        content = client.download_repo_file(username, name, rfile.path, binary=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        changes += 1
        logger.info("  Downloaded: %s", rfile.path)

    # Delete local files that no longer exist on remote.
    for rel in sorted(local_paths - remote_paths):
        target = (root / rel).resolve()
        if not target.is_relative_to(resolved_root):
            continue
        if target.exists():
            target.unlink()
            changes += 1
            logger.info("  Deleted: %s", rel)

    return changes


