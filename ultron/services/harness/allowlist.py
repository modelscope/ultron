# Copyright (c) ModelScope Contributors. All rights reserved.
import fnmatch
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Type

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB


class ClawWorkspaceAllowlist(ABC):
    """Abstract base for Claw-product workspace file allowlists."""

    @property
    @abstractmethod
    def product_name(self) -> str:
        ...

    @property
    @abstractmethod
    def workspace_root(self) -> Path:
        ...

    @property
    @abstractmethod
    def patterns(self) -> List[str]:
        ...

    def _matches(self, rel_path: str) -> bool:
        for pattern in self.patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
        return False

    def collect(self) -> Dict[str, str]:
        """Gather allowed workspace files as {relative_path: text_content}."""
        root = self.workspace_root
        if not root.is_dir():
            return {}
        result: Dict[str, str] = {}
        for f in sorted(root.rglob("*")):
            if not f.is_file() or f.is_symlink():
                continue
            try:
                rel = str(f.relative_to(root))
            except ValueError:
                continue
            if any(part.startswith(".") for part in Path(rel).parts):
                continue
            if not self._matches(rel):
                continue
            try:
                if f.stat().st_size > MAX_FILE_SIZE:
                    continue
                result[rel] = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                logger.debug("Skip %s: %s", f, e)
        return result

    def apply(self, resources: Dict[str, str]) -> List[str]:
        """Write resource files back to the workspace. Returns list of written paths."""
        root = self.workspace_root.resolve()
        written: List[str] = []
        for rel_path, content in resources.items():
            target = (root / rel_path).resolve()
            if not str(target).startswith(str(root)):
                logger.warning("Path traversal blocked: %s", rel_path)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written.append(str(target))
        return written


class NanobotWorkspaceAllowlist(ClawWorkspaceAllowlist):
    """Allowlist for the nanobot agent workspace."""

    @property
    def product_name(self) -> str:
        return "nanobot"

    @property
    def workspace_root(self) -> Path:
        return Path.home() / ".nanobot" / "workspace"

    @property
    def patterns(self) -> List[str]:
        return [
            "AGENTS.md",
            "SOUL.md",
            "USER.md",
            "TOOLS.md",
            "HEARTBEAT.md",
            "memory/MEMORY.md",
            "memory/HISTORY.md",
            "skills/*/SKILL.md",
            "skills/*/_meta.json",
            "skills/*/scripts/*",
            "skills/*/setup.md",
            "skills/*/operations.md",
            "skills/*/boundaries.md",
        ]


class OpenclawWorkspaceAllowlist(ClawWorkspaceAllowlist):
    """Allowlist for the OpenClaw agent workspace."""

    @property
    def product_name(self) -> str:
        return "openclaw"

    @property
    def workspace_root(self) -> Path:
        return Path.home() / ".openclaw" / "workspace"

    @property
    def patterns(self) -> List[str]:
        return [
            "AGENTS.md",
            "SOUL.md",
            "USER.md",
            "TOOLS.md",
            "HEARTBEAT.md",
            "IDENTITY.md",
            "BOOTSTRAP.md",
            "MEMORY.md",
            "memory/*.md",
            "memory/*.json",
            "skills/*/SKILL.md",
            "skills/*/_meta.json",
            "skills/*/scripts/*",
        ]


class HermesWorkspaceAllowlist(ClawWorkspaceAllowlist):
    """Allowlist for the Hermes agent workspace."""

    @property
    def product_name(self) -> str:
        return "hermes"

    @property
    def workspace_root(self) -> Path:
        return Path.home() / ".hermes"

    @property
    def patterns(self) -> List[str]:
        return [
            "SOUL.md",
            "memories/*.md",
            "skills/*/SKILL.md",
            "skills/*/DESCRIPTION.md",
            "skills/*/_meta.json",
            "skills/*/scripts/*",
            "skills/*/references/*",
            "skills/*/*/SKILL.md",
            "skills/*/*/_meta.json",
            "skills/*/*/scripts/*",
            "skills/*/*/references/*",
        ]


ALLOWLIST_REGISTRY: Dict[str, Type[ClawWorkspaceAllowlist]] = {
    "nanobot": NanobotWorkspaceAllowlist,
    "openclaw": OpenclawWorkspaceAllowlist,
    "hermes": HermesWorkspaceAllowlist,
}
