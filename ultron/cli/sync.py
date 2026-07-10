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



def zip_resources(resources: Dict[str, Union[str, bytes]], wrapper: str = "") -> bytes:
    """Pack resources into a deterministic in-memory zip for local backup.

    Entries are stored with workspace-relative paths (no wrapper directory) so
    that restore can extract them back to the exact locations reported by
    ``collect``/``apply``.  Used by :func:`backup_local` to create timestamped
    backups before destructive operations (pull, convert, restore).

    Args:
        resources: A dict {rel_path: content}. Values are written directly
                   via ``ZipFile.writestr`` (accepts both str and bytes).
        wrapper: Optional top-level wrapper directory (kept only for backward
                 compatibility; empty by default).
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, value in sorted(resources.items()):
            key = f"{wrapper}/{rel}" if wrapper else rel
            zf.writestr(key, value)
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
) -> Dict[str, Union[bytes, None]]:
    """Compare local files against the sync baseline sha256 map.

    Returns a dict of files that differ:
      - key present with bytes value: content changed or file is new locally
      - key present with None value: file was deleted locally (in baseline but not local)
    """
    changed: Dict[str, Union[bytes, None]] = {}
    # Modified or new files.
    for rel, content in local_resources.items():
        local_sha = sha256_content(content)
        if baseline_sha256.get(rel) != local_sha:
            changed[rel] = content
    # Deleted files (in baseline but not in local).
    for rel in baseline_sha256:
        if rel not in local_resources:
            changed[rel] = None
    return changed


def _retry_on_master_missing(fn, retries: int = 3, delay: float = 2.0):
    """Run *fn*, retrying the create-then-commit race.

    A freshly created repo may not have its ``master`` branch ready when the
    first commit fires, yielding a 400 "branch or revision master not found".
    Wrapping any commit-bearing call (normal commit *and* LFS upload) means
    every first-push path gets the same protection.
    """
    import time

    from .client import ApiError

    for attempt in range(retries):
        try:
            return fn()
        except ApiError as e:
            msg = (getattr(e, "detail", "") or getattr(e, "message", "") or str(e)).lower()
            branch_missing = getattr(e, "status", None) == 400 and (
                "branch" in msg or "revision" in msg
            )
            if branch_missing and attempt < retries - 1:
                time.sleep(delay)
                continue
            raise


def push_resources(
    client: "UltronClient",
    username: str,
    name: str,
    framework: str,
    resources: Dict[str, bytes],
) -> None:
    """Full upload via commit interface (normal + LFS).

    Creates the repo if needed, then commits all files in batches.
    Raises on failure (caller should NOT update baseline on exception).
    """
    from .client import is_lfs_file

    if not resources:
        logger.warning("push_resources called with empty resources; skipping.")
        return

    # Ensure repo exists (idempotent create).
    try:
        if not client.check_repo(username, name):
            client.create_repo(username, name, framework=framework)
            logger.info("Created empty agent repo %s/%s (framework=%s).", username, name, framework)
    except Exception as exc:
        logger.warning("create_repo check failed (%s), proceeding anyway.", exc)

    # Split into normal and LFS files.
    normal_actions: List[dict] = []
    lfs_files: List[tuple] = []

    for rel, content in sorted(resources.items()):
        size = len(content)
        if is_lfs_file(rel, size):
            lfs_files.append((rel, content))
        else:
            b64 = base64.b64encode(content).decode("ascii")
            normal_actions.append({
                "action": "create",
                "path": rel,
                "type": "normal",
                "size": size,
                "sha256": "",
                "content": b64,
                "encoding": "base64",
            })

    # Commit normal files in one request.
    if normal_actions:
        _retry_on_master_missing(lambda: client.commit_files(
            username, name, normal_actions,
            commit_message="sync: upload normal files"))
        for a in normal_actions:
            logger.info("  CREATE: %s (%d B)", a["path"], a["size"])

    # Upload LFS files one-by-one (batch verify + PUT + commit).  The commit
    # inside upload_lfs_file hits the same fresh-repo master race, so it needs
    # the retry too (LFS-only first push would otherwise fail).
    for rel, content in lfs_files:
        _retry_on_master_missing(lambda rel=rel, content=content: client.upload_lfs_file(
            username, name, rel, content,
            action="create", commit_message=f"sync: upload LFS {rel}"))
        logger.info("  CREATE (LFS): %s (%d B)", rel, len(content))

    logger.info("Pushed %d file(s) (%d normal, %d LFS).",
                len(resources), len(normal_actions), len(lfs_files))


def push_incremental(
    client: "UltronClient",
    username: str,
    name: str,
    changed: Dict[str, Union[bytes, None]],
    remote_paths: set,
    remote_lfs_paths: set = None,
) -> None:
    """Incremental push via commit interface.

    Builds create/update/delete actions and commits.  LFS files are
    uploaded via the LFS batch+PUT flow before committing their reference.
    """
    from .client import is_lfs_file

    normal_actions: List[dict] = []
    lfs_items: List[tuple] = []  # (path, content, action_type)
    delete_paths: List[str] = []

    for fpath, content in changed.items():
        if content is None:
            delete_paths.append(fpath)
        else:
            action_type = "update" if fpath in remote_paths else "create"
            size = len(content)
            # Determine if the file needs LFS: check remote flag or local heuristic.
            use_lfs = False
            if remote_lfs_paths and fpath in remote_lfs_paths:
                use_lfs = True
            elif is_lfs_file(fpath, size):
                use_lfs = True

            if use_lfs:
                lfs_items.append((fpath, content, action_type))
            else:
                b64 = base64.b64encode(content).decode("ascii")
                normal_actions.append({
                    "action": action_type,
                    "path": fpath,
                    "type": "normal",
                    "size": size,
                    "sha256": "",
                    "content": b64,
                    "encoding": "base64",
                })

    # Commit normal file actions in one batch.
    if normal_actions:
        for a in normal_actions:
            logger.info("  %s: %s", a["action"].upper(), a["path"])
        client.commit_files(username, name, normal_actions,
                            commit_message="watch sync")

    # Upload LFS files one-by-one.
    for fpath, content, action_type in lfs_items:
        logger.info("  %s (LFS): %s", action_type.upper(), fpath)
        client.upload_lfs_file(username, name, fpath, content,
                              action=action_type, commit_message="watch sync")

    # Delete files via the DELETE endpoint.
    for fpath in delete_paths:
        logger.info("  DELETE: %s", fpath)
        client.delete_file(username, name, fpath)

    total = len(normal_actions) + len(lfs_items) + len(delete_paths)
    if total:
        logger.info("Committed %d action(s) incrementally.", total)


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


