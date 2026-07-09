# Copyright (c) ModelScope Contributors. All rights reserved.
"""Per-product workspace file allowlists.

Each "Claw product" (agent framework) stores its files in a known on-disk
layout. A subclass of :class:`ClawWorkspaceAllowlist` declares, for one product,
*where* the files live (``workspace_root``) and *which* of them are portable
(``patterns``). ``collect()`` walks the workspace and returns
``{workspace_relative_path: text_content}``; the stored paths are always
workspace-relative regardless of the on-disk directory model, so the server,
``merge.py`` and the dashboard all operate on the same key space.

Sub-agents
----------
A single installation can host several sub-agents. There are three layouts:

* **root-per-agent** -- the sub-agent *is* a directory; selecting it changes
  ``workspace_root`` (qwenpaw ``workspaces/<name>``, openclaw
  ``workspace-<name>``).
* **file-per-agent + shared** -- the sub-agent is one file inside a shared root,
  collected alongside the shared resources; a ``{name}`` placeholder in
  ``patterns`` is formatted with the sub-agent name so only the selected agent's
  file matches (qoder ``agents/<name>.md``).
* **single-agent** -- one persona per install; the sub-agent name is only the
  repository identity and does not affect file selection (hermes, openhuman,
  nanobot, ms-agent).

The dashboard re-implements the same root/pattern logic in TypeScript
(``ultron/dashboard/src/components/harness/UploadWorkspace.tsx``); keep the two
in sync when changing a layout.
"""
import fnmatch
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Type

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 1 * 1024 * 1024  # 1 MB

DEFAULT_AGENT_NAME = "default"
ALL_AGENT_NAME = "all"
GLOBAL_AGENT_NAME = "__global__"


class ClawWorkspaceAllowlist(ABC):
    """Abstract base for Claw-product workspace file allowlists.

    :param agent_name: the sub-agent to operate on. Used to resolve
        ``workspace_root`` (root-per-agent products) and/or to format ``{name}``
        placeholders in ``patterns`` (file-per-agent products). Ignored for
        single-agent products.

        The special value ``"all"`` selects *every* sub-agent at once.  For
        file-per-agent products this simply wildcards the ``{name}`` placeholder;
        for root-per-agent products it lifts ``workspace_root`` one level up and
        prefixes patterns so that each agent's files live under its own sub-path.

    :param local_dir: explicit workspace root override; when given, it replaces
        the product's default ``workspace_root`` (used by ``ultron upload
        --local_dir``).
    """

    def __init__(
        self, agent_name: str = DEFAULT_AGENT_NAME, local_dir: Optional[Path] = None
    ):
        self.agent_name = agent_name or DEFAULT_AGENT_NAME
        self._local_dir = Path(local_dir).expanduser() if local_dir else None

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def product_name(self) -> str:
        ...

    @property
    @abstractmethod
    def default_workspace_root(self) -> Path:
        """Workspace root for ``self.agent_name`` (before ``local_dir`` override)."""
        ...

    @property
    @abstractmethod
    def patterns(self) -> List[str]:
        """fnmatch globs (workspace-relative); may contain ``{name}``."""
        ...

    # ------------------------------------------------------------------
    # All-mode & watch constraint
    # ------------------------------------------------------------------

    def _is_all(self) -> bool:
        """Whether we are in 'all sub-agents' mode."""
        return self.agent_name == ALL_AGENT_NAME

    @property
    def supports_individual_watch(self) -> bool:
        """Whether ``watch`` supports a single sub-agent name.

        File-per-agent+shared products must override this to ``False`` because
        shared files would cascade changes between repos.
        """
        return True

    def _effective_patterns(self) -> List[str]:
        """Patterns to match against.  Root-per-agent classes override this to
        add an agent-name prefix in all mode."""
        return self.patterns

    # ------------------------------------------------------------------
    # All-mode path prefixing (for cross-framework conversion)
    # ------------------------------------------------------------------

    @property
    def is_root_per_agent(self) -> bool:
        """Whether sub-agents are separate directories (root-per-agent layout).

        All-mode cross-framework conversion is only well-defined between two
        root-per-agent frameworks, where every agent maps 1:1 to a directory
        prefix.  Other layouts return ``False``.
        """
        return False

    def split_all_path(self, rel_path: str) -> Tuple[Optional[str], str]:
        """Split an all-mode path into ``(agent_name, bare_path)``.

        ``bare_path`` is the path relative to a single agent's root.  Returns
        ``(None, rel_path)`` when the path has no recognizable agent prefix
        (e.g. top-level ``README.md``).  Root-per-agent classes override this.
        """
        return (None, rel_path)

    def join_all_path(self, agent_name: str, bare_path: str) -> str:
        """Inverse of :meth:`split_all_path`: build this framework's all-mode
        path for *agent_name* + *bare_path*."""
        return bare_path

    # ------------------------------------------------------------------
    # Core helpers
    # ------------------------------------------------------------------

    @property
    def workspace_root(self) -> Path:
        """Effective root: ``local_dir`` override, else the product default."""
        return self._local_dir if self._local_dir is not None else self.default_workspace_root

    def _is_global(self) -> bool:
        """Whether we are in global-only mode (shared files only, no sub-agent)."""
        return self.agent_name == GLOBAL_AGENT_NAME

    def resolved_patterns(self) -> List[str]:
        """Resolve glob patterns for the current agent mode.

        Convention: In global mode (``GLOBAL_AGENT_NAME``), patterns containing
        the ``{name}`` placeholder are excluded because they target specific
        sub-agents.  Shared/framework-level patterns (those without ``{name}``)
        remain.  New frameworks MUST follow this convention: use ``{name}`` in
        patterns that are per-agent and omit it for shared/global patterns.
        """
        if self._is_global():
            # Global mode: exclude patterns containing {name} placeholder.
            return [p for p in self._effective_patterns() if "{name}" not in p]
        name = "*" if self._is_all() else self.agent_name
        return [p.format(name=name) for p in self._effective_patterns()]

    def matches(self, rel_path: str, patterns: List[str]) -> bool:
        """Return True if *rel_path* matches any of the given glob *patterns*."""
        for pattern in patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
        return False

    def _walk_matched(self) -> List[Tuple[str, Path]]:
        """Walk workspace and return (rel_path, Path) for matched files."""
        root = self.workspace_root
        if not root.is_dir():
            return []
        patterns = self.resolved_patterns()
        matched: List[Tuple[str, Path]] = []
        for dirpath, dirnames, filenames in os.walk(root):
            # Skip hidden directories in-place (prevents descending into them).
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for fname in sorted(filenames):
                if fname.startswith("."):
                    continue
                f = Path(dirpath) / fname
                if f.is_symlink():
                    continue
                try:
                    rel = f.relative_to(root).as_posix()
                except ValueError:
                    continue
                if not self.matches(rel, patterns):
                    continue
                try:
                    if f.stat().st_size > MAX_FILE_SIZE:
                        continue
                except OSError:
                    continue
                matched.append((rel, f))
        return matched

    def collect(self) -> Dict[str, str]:
        """Gather allowed workspace files as {relative_path: text_content}."""
        result: Dict[str, str] = {}
        for rel, f in self._walk_matched():
            try:
                result[rel] = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                logger.warning("Skip %s: %s", f, e)
        return result

    def collect_bytes(self) -> Dict[str, bytes]:
        """Gather allowed workspace files as {relative_path: raw_bytes}.

        Unlike :meth:`collect`, this includes binary files (images, PDFs, etc.)
        and does not skip on UnicodeDecodeError.
        """
        result: Dict[str, bytes] = {}
        for rel, f in self._walk_matched():
            try:
                result[rel] = f.read_bytes()
            except OSError as e:
                logger.warning("Skip %s: %s", f, e)
        return result

    def list_agents(self) -> List[str]:
        """Discover sub-agent names available on disk.

        Default: single-agent products report ``["default"]``. Root-per-agent and
        file-per-agent products override this to enumerate their layout.
        """
        return [DEFAULT_AGENT_NAME]

    def _list_agents_from_dir(self, agents_dir: Path) -> List[str]:
        """List agents from a directory, prepending DEFAULT if not present."""
        agents = _list_agent_files(agents_dir)
        if DEFAULT_AGENT_NAME not in agents:
            agents = [DEFAULT_AGENT_NAME] + agents
        return agents

    def apply(self, resources: Dict[str, str]) -> List[str]:
        """Write resource files back to the workspace. Returns list of written paths."""
        root = self.workspace_root.resolve()
        written: List[str] = []
        for rel_path, content in resources.items():
            target = (root / rel_path).resolve()
            if not target.is_relative_to(root):
                logger.warning("Path traversal blocked: %s", rel_path)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written.append(str(target))
        return written


class NanobotWorkspaceAllowlist(ClawWorkspaceAllowlist):
    """Allowlist for the nanobot agent workspace (single-agent install).

    Nanobot keeps a single shared workspace at ``~/.nanobot/workspace``; its
    sub-agents run as background sessions with no on-disk per-agent files, so
    this is a single-agent layout (the agent name is only the repo identity).
    """

    @property
    def product_name(self) -> str:
        return "nanobot"

    @property
    def default_workspace_root(self) -> Path:
        return Path.home() / ".nanobot" / "workspace"

    @property
    def patterns(self) -> List[str]:
        return [
            "AGENTS.md",
            "SOUL.md",
            "USER.md",
            "HEARTBEAT.md",
            "memory/MEMORY.md",
            "memory/HISTORY.md",
            "skills/*/SKILL.md",
            "skills/*/scripts/*",
        ]


class OpenclawWorkspaceAllowlist(ClawWorkspaceAllowlist):
    """Allowlist for the OpenClaw agent workspace (root-per-agent).

    The default agent lives in ``~/.openclaw/workspace``; named agents live in
    ``~/.openclaw/workspace-<name>``.

    In ``all`` mode, ``workspace_root`` lifts to ``~/.openclaw/`` and patterns
    are prefixed with ``workspace*/`` to match both ``workspace/`` (default) and
    ``workspace-<name>/`` directories.
    """

    @property
    def product_name(self) -> str:
        return "openclaw"

    @property
    def default_workspace_root(self) -> Path:
        base = Path.home() / ".openclaw"
        if self._is_all():
            return base
        if self.agent_name in ("", DEFAULT_AGENT_NAME):
            return base / "workspace"
        return base / f"workspace-{self.agent_name}"

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

    def _effective_patterns(self) -> List[str]:
        if self._is_all():
            return [f"workspace*/{p}" for p in self.patterns]
        return self.patterns

    @property
    def is_root_per_agent(self) -> bool:
        return True

    def split_all_path(self, rel_path: str) -> Tuple[Optional[str], str]:
        # agent lives in ``workspace/`` (default) or ``workspace-<name>/``.
        if "/" not in rel_path:
            return (None, rel_path)
        head, rest = rel_path.split("/", 1)
        if head == "workspace":
            return (DEFAULT_AGENT_NAME, rest)
        if head.startswith("workspace-"):
            return (head[len("workspace-"):], rest)
        return (None, rel_path)

    def join_all_path(self, agent_name: str, bare_path: str) -> str:
        if agent_name in ("", DEFAULT_AGENT_NAME):
            return f"workspace/{bare_path}"
        return f"workspace-{agent_name}/{bare_path}"

    def list_agents(self) -> List[str]:
        base = Path.home() / ".openclaw"
        agents: List[str] = []
        if (base / "workspace").is_dir():
            agents.append(DEFAULT_AGENT_NAME)
        if base.is_dir():
            for d in sorted(base.glob("workspace-*")):
                if d.is_dir():
                    agents.append(d.name[len("workspace-"):])
        return agents or [DEFAULT_AGENT_NAME]


class HermesWorkspaceAllowlist(ClawWorkspaceAllowlist):
    """Allowlist for the Hermes agent workspace (single-agent install)."""

    @property
    def product_name(self) -> str:
        return "hermes"

    @property
    def default_workspace_root(self) -> Path:
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


class QwenpawWorkspaceAllowlist(ClawWorkspaceAllowlist):
    """Allowlist for the QwenPaw agent workspace (root-per-agent).

    QwenPaw stores per-agent workspaces under ``~/.qwenpaw/workspaces/{id}``;
    the default agent lives in ``workspaces/default``.

    In ``all`` mode, ``workspace_root`` lifts to ``~/.qwenpaw/workspaces/`` and
    patterns are prefixed with ``*/`` so that each agent directory becomes a
    path prefix in the collected resource dict.
    """

    @property
    def product_name(self) -> str:
        return "qwenpaw"

    @property
    def default_workspace_root(self) -> Path:
        base = Path.home() / ".qwenpaw" / "workspaces"
        if self._is_all():
            return base
        return base / self.agent_name

    @property
    def patterns(self) -> List[str]:
        return [
            "AGENTS.md",
            "SOUL.md",
            "PROFILE.md",
            "BOOTSTRAP.md",
            "MEMORY.md",
            "HEARTBEAT.md",
            "memory/*.md",
            "skills/*/SKILL.md",
            "skills/*/_meta.json",
            "skills/*/scripts/*",
        ]

    def _effective_patterns(self) -> List[str]:
        if self._is_all():
            return [f"*/{p}" for p in self.patterns]
        return self.patterns

    @property
    def is_root_per_agent(self) -> bool:
        return True

    def split_all_path(self, rel_path: str) -> Tuple[Optional[str], str]:
        # agent directory name IS the agent name: ``<agent>/<bare>``.
        if "/" in rel_path:
            head, rest = rel_path.split("/", 1)
            return (head, rest)
        return (None, rel_path)

    def join_all_path(self, agent_name: str, bare_path: str) -> str:
        return f"{agent_name}/{bare_path}"

    def list_agents(self) -> List[str]:
        base = Path.home() / ".qwenpaw" / "workspaces"
        if not base.is_dir():
            return [DEFAULT_AGENT_NAME]
        agents = [d.name for d in sorted(base.iterdir()) if d.is_dir()]
        return agents or [DEFAULT_AGENT_NAME]


class OpenhumanWorkspaceAllowlist(ClawWorkspaceAllowlist):
    """Allowlist for the OpenHuman agent workspace (single-agent install).

    OpenHuman is a Rust/Tauri desktop app whose brain is a local Memory Tree
    mirrored as an Obsidian-style ``wiki/`` Markdown vault. Only the
    human-readable ``wiki/`` vault is portable; OpenHuman has no OpenClaw-style
    persona files (SOUL/IDENTITY/USER/...).
    """

    @property
    def product_name(self) -> str:
        return "openhuman"

    @property
    def default_workspace_root(self) -> Path:
        return Path.home() / ".openhuman" / "workspace"

    @property
    def patterns(self) -> List[str]:
        # ``*`` in fnmatch spans ``/`` so this recurses the whole wiki vault.
        return [
            "wiki/*.md",
        ]


class QoderWorkspaceAllowlist(ClawWorkspaceAllowlist):
    """Allowlist for the Qoder agent workspace (file-per-agent + shared).

    Qoder keeps user-level config at ``~/.qoder`` (project-level config lives in
    a project's ``.qoder/`` directory; point ``--local_dir`` at it to upload
    that instead). A sub-agent is one Markdown file ``agents/<name>.md``; skills,
    commands, rules and ``AGENTS.md`` are shared across sub-agents.
    """

    @property
    def product_name(self) -> str:
        return "qoder"

    @property
    def supports_individual_watch(self) -> bool:
        return False

    @property
    def default_workspace_root(self) -> Path:
        return Path.home() / ".qoder"

    @property
    def patterns(self) -> List[str]:
        return [
            "AGENTS.md",
            "agents/{name}.md",
            "commands/*.md",
            "rules/*.md",
            "skills/*/SKILL.md",
            "skills/*/scripts/*",
            "skills/*/references/*",
        ]

    def list_agents(self) -> List[str]:
        return self._list_agents_from_dir(self.workspace_root / "agents")


class MsAgentWorkspaceAllowlist(ClawWorkspaceAllowlist):
    """Allowlist for the ms-agent agent workspace (single-agent install).

    ms-agent keeps its persona, memory and skills under ``~/.ms_agent``:

    * **persona** -- a single ``profile.md`` augmented by injected
      configuration (project-level ``config.yaml``, global ``settings.json``
      and a user-specified ``agent.yaml``).
    * **memory** -- ``MEMORY.md`` plus a structured ``facts.json``.
    * **skills** -- ``skills/<name>/SKILL.md`` with a workspace-level
      ``skill.json`` metadata index.

    Only ``profile.md`` (persona) and ``MEMORY.md`` (memory) carry
    cross-framework semantics; the YAML/JSON config and metadata files are
    ms-agent specific and are preserved on same-framework sync only.
    """

    @property
    def product_name(self) -> str:
        return "ms-agent"

    @property
    def default_workspace_root(self) -> Path:
        return Path.home() / ".ms_agent"

    @property
    def patterns(self) -> List[str]:
        return [
            # Persona + injected configuration
            "profile.md",
            "config.yaml",
            "settings.json",
            "agent.yaml",
            # Memory
            "MEMORY.md",
            "facts.json",
            # Skills
            "skill.json",
            "skills/*/SKILL.md",
        ]


def _list_agent_files(agents_dir: Path) -> List[str]:
    """Return the stems of ``*.md`` files in an ``agents/`` directory."""
    if not agents_dir.is_dir():
        return []
    return sorted(f.stem for f in agents_dir.glob("*.md") if f.is_file())


ALLOWLIST_REGISTRY: Dict[str, Type[ClawWorkspaceAllowlist]] = {
    "nanobot": NanobotWorkspaceAllowlist,
    "openclaw": OpenclawWorkspaceAllowlist,
    "hermes": HermesWorkspaceAllowlist,
    "qwenpaw": QwenpawWorkspaceAllowlist,
    "openhuman": OpenhumanWorkspaceAllowlist,
    "qoder": QoderWorkspaceAllowlist,
    "ms-agent": MsAgentWorkspaceAllowlist,
}
