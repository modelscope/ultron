# Copyright (c) ModelScope Contributors. All rights reserved.
"""Core sync logic: backup, download, diff, apply."""
import hashlib
import io
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from .cache import cache_dir, cloud_dir


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


def zip_resources(resources: Dict[str, str]) -> bytes:
    """Pack resources into a deterministic in-memory zip.

    Args:
        resources: A dict {rel_path: content_or_filepath}. If a value is a
                   short string that points to an existing file on disk, its
                   content is read; otherwise the value is treated as literal
                   text content.
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
            zf.writestr(rel, content)
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

