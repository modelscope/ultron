# Copyright (c) ModelScope Contributors. All rights reserved.
"""Core sync logic: backup, download, diff, apply, bidirectional sync helpers."""
import hashlib
import io
import logging
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List

from .cache import cache_dir, cloud_dir

if TYPE_CHECKING:
    from .client import RemoteFileInfo, UltronClient

logger = logging.getLogger("ultron.watch")


@dataclass
class DiffResult:
    """Result of comparing local files against cloud files."""

    to_delete: List[str] = field(default_factory=list)
    to_add: List[str] = field(default_factory=list)
    to_overwrite: List[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.to_delete and not self.to_add and not self.to_overwrite


def _md5(content: str) -> str:
    return hashlib.md5(content.encode("utf-8")).hexdigest()


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
            content = value
            # Only attempt path resolution for short values that have no
            # newlines (newlines are a strong signal of literal content).
            if isinstance(value, str) and len(value) < 4096 and "\n" not in value:
                try:
                    p = Path(value)
                    if p.is_file():
                        content = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    pass
            zf.writestr(f"{wrapper}/{rel}", content)
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


def download_cloud(client, username: str, name: str) -> Dict[str, str]:
    """Download all files from the cloud repo into the local cloud cache.

    Returns ``{rel_path: content}`` mapping.
    """
    paths = client.list_repo_files(username, name)
    cloud = cloud_dir(name)
    resources: Dict[str, str] = {}
    for p in paths:
        content = client.download_repo_file(username, name, p)
        resources[p] = content
        # Persist to cloud cache directory.
        file_path = cloud / p
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
    return resources


def diff_files(local: Dict[str, str], cloud: Dict[str, str]) -> DiffResult:
    """Compare local files against cloud files.

    - ``to_delete``: files in local but not in cloud (local extras).
    - ``to_add``: files in cloud but not in local (missing locally).
    - ``to_overwrite``: files in both but with different MD5.
    """
    local_keys = set(local.keys())
    cloud_keys = set(cloud.keys())
    result = DiffResult(
        to_delete=sorted(local_keys - cloud_keys),
        to_add=sorted(cloud_keys - local_keys),
    )
    for key in sorted(local_keys & cloud_keys):
        if _md5(local[key]) != _md5(cloud[key]):
            result.to_overwrite.append(key)
    return result


def apply_sync(spec, diff: DiffResult, cloud: Dict[str, str], backup_path: Path) -> int:
    """Apply the diff to the local workspace.

    - Delete local extras
    - Overwrite files with different MD5
    - Add files that exist only on cloud

    Returns the total number of changes applied.
    """
    root: Path = spec.workspace_root
    changes = 0

    for rel in diff.to_delete:
        target = root / rel
        if target.exists():
            target.unlink()
            print(f"  Deleted: {rel}  (backup at {backup_path})")
            changes += 1

    for rel in diff.to_overwrite:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(cloud[rel], encoding="utf-8")
        print(f"  Overwritten: {rel}  (backup at {backup_path})")
        changes += 1

    for rel in diff.to_add:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(cloud[rel], encoding="utf-8")
        print(f"  Added: {rel}")
        changes += 1

    return changes


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


