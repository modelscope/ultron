# Copyright (c) ModelScope Contributors. All rights reserved.
"""Core sync logic: backup, zip, bidirectional sync helpers."""
import hashlib
import io
import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List

from .cache import cache_dir

if TYPE_CHECKING:
    from .client import RemoteFileInfo, UltronClient

logger = logging.getLogger("ultron.watch")



def zip_resources(resources: Dict[str, str], wrapper: str = "agent") -> bytes:
    """Pack resources into a deterministic in-memory zip.

    The server always strips the first directory level from zip entries, so we
    wrap all files under a top-level folder (``wrapper/``). This ensures that
    after stripping, the remaining path matches the original ``rel_path``.

    Args:
        resources: A dict {rel_path: content_or_filepath}. If a value is a
                   short string that points to an existing file on disk, its
                   content is read; otherwise the value is treated as literal
                   text content.
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
    resources: Dict[str, str] = spec.collect()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = cache_dir() / f"{name}_{timestamp}.zip"
    zip_path.write_bytes(zip_resources(resources))
    return zip_path



# ---- Bidirectional sync helpers ----

def sha256_content(content: str) -> str:
    """Compute sha256 of text content (utf-8 encoded, no BOM)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def detect_local_changes(
    local_resources: Dict[str, str],
    baseline_sha256: Dict[str, str],
) -> Dict[str, str]:
    """Compare local files against the sync baseline sha256 map.

    Returns a dict of files that differ:
      - key present with non-empty value: content changed or file is new locally
      - key present with empty string value: file was deleted locally (in baseline but not local)
    """
    changed: Dict[str, str] = {}
    # Modified or new files.
    for rel, content in local_resources.items():
        local_sha = sha256_content(content)
        if baseline_sha256.get(rel) != local_sha:
            changed[rel] = content
    # Deleted files (in baseline but not in local).
    for rel in baseline_sha256:
        if rel not in local_resources:
            changed[rel] = ""
    return changed


def push_resources(
    client: "UltronClient",
    username: str,
    name: str,
    framework: str,
    resources: Dict[str, str],
) -> None:
    """Zip, upload, and create/update the remote agent repo.

    Raises on failure (caller should NOT update baseline on exception).
    """
    zip_bytes = zip_resources(resources)
    file_id = client.upload_file(zip_bytes)
    client.create_repo(username, name, framework, system_prompt_files=file_id)
    logger.info("Pushed %d file(s) (%d bytes zip).", len(resources), len(zip_bytes))


def pull_incremental(
    client: "UltronClient",
    username: str,
    name: str,
    spec,
    remote_files: "List[RemoteFileInfo]",
    local_resources: Dict[str, str],
) -> int:
    """Incrementally pull remote changes to local workspace.

    Compares remote sha256 with local content sha256:
      - remote has file & sha256 differs (or local missing) → download & write
      - local has file & remote doesn't → delete local

    Returns the number of files changed. Raises if any download fails
    (caller should NOT update baseline on exception).
    """
    root: Path = spec.workspace_root
    remote_sha_map = {f.path: f.sha256 for f in remote_files}
    remote_paths = set(remote_sha_map.keys())
    local_paths = set(local_resources.keys())
    changes = 0

    # Download files that are new or changed on remote.
    for rfile in remote_files:
        local_content = local_resources.get(rfile.path)
        if local_content is not None:
            local_sha = sha256_content(local_content)
            if local_sha == rfile.sha256:
                continue  # identical, skip
        # Need to download.
        content = client.download_repo_file(username, name, rfile.path)
        target = root / rfile.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        changes += 1
        logger.info("  Downloaded: %s", rfile.path)

    # Delete local files that no longer exist on remote.
    for rel in sorted(local_paths - remote_paths):
        target = root / rel
        if target.exists():
            target.unlink()
            changes += 1
            logger.info("  Deleted: %s", rel)

    return changes


