# Copyright (c) ModelScope Contributors. All rights reserved.
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_PRESETS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "soul_presets"

_SOUL_HEADER_KEYWORDS = re.compile(
    r"identity|communication|style|critical.rule|rules.you.must.follow",
    re.IGNORECASE,
)


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _parse_frontmatter(text: str) -> tuple:
    """Return (metadata_dict, body_str). Metadata keys are lowercased."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta: dict = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            val = val.strip().strip("'\"")
            meta[key.strip().lower()] = val
    return meta, parts[2].lstrip("\n")


def _split_body_for_openclaw(meta: dict, body: str) -> Dict[str, str]:
    """Split agent body into SOUL.md + AGENTS.md + IDENTITY.md (OpenClaw convention)."""
    soul_parts: list[str] = []
    agents_parts: list[str] = []
    current_target = "agents"
    current_section = ""

    for line in body.splitlines(keepends=True):
        if line.startswith("## "):
            if current_section:
                (soul_parts if current_target == "soul" else agents_parts).append(
                    current_section
                )
            current_section = ""
            current_target = (
                "soul" if _SOUL_HEADER_KEYWORDS.search(line) else "agents"
            )
        current_section += line

    if current_section:
        (soul_parts if current_target == "soul" else agents_parts).append(
            current_section
        )

    result: Dict[str, str] = {}
    if soul_parts:
        result["SOUL.md"] = "".join(soul_parts)
    if agents_parts:
        result["AGENTS.md"] = "".join(agents_parts)

    emoji = meta.get("emoji", "")
    name = meta.get("name", "")
    vibe = meta.get("vibe", "")
    if emoji and vibe:
        result["IDENTITY.md"] = f"# {emoji} {name}\n{vibe}\n"
    elif name:
        result["IDENTITY.md"] = f"# {name}\n{meta.get('description', '')}\n"

    return result


class SoulPresetService:
    """Loads, caches, and serves soul preset templates from disk."""

    def __init__(self, presets_dir: Optional[Path] = None):
        self._dir = presets_dir or _PRESETS_DIR
        self._cache: Dict[str, dict] = {}
        self._categories: Dict[str, List[dict]] = {}
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            self.load()

    def load(self):
        """Scan presets directory and cache metadata + raw content."""
        self._cache.clear()
        self._categories.clear()

        if not self._dir.is_dir():
            logger.warning("Soul presets directory not found: %s", self._dir)
            self._loaded = True
            return

        for md_file in sorted(self._dir.rglob("*.md")):
            if md_file.name.lower() == "readme.md":
                continue
            raw = md_file.read_text(encoding="utf-8")
            meta, body = _parse_frontmatter(raw)
            if not meta.get("name"):
                continue

            category = md_file.parent.name
            preset_id = f"{category}-{_slugify(meta['name'])}"

            entry = {
                "id": preset_id,
                "name": meta["name"],
                "description": meta.get("description", ""),
                "emoji": meta.get("emoji", ""),
                "color": meta.get("color", ""),
                "vibe": meta.get("vibe", ""),
                "category": category,
                "body": body,
                "meta": meta,
            }
            self._cache[preset_id] = entry
            self._categories.setdefault(category, []).append(
                {
                    "id": preset_id,
                    "name": meta["name"],
                    "description": meta.get("description", ""),
                    "emoji": meta.get("emoji", ""),
                }
            )

        self._loaded = True
        logger.info(
            "Loaded %d soul presets across %d categories",
            len(self._cache),
            len(self._categories),
        )

    def list_presets(self) -> List[dict]:
        """Return categories with their preset metadata (no body content)."""
        self._ensure_loaded()
        return [
            {"id": cat, "label": cat.replace("-", " ").title(), "presets": presets}
            for cat, presets in sorted(self._categories.items())
        ]

    def get_preset(self, preset_id: str) -> Optional[dict]:
        """Return full preset entry including body, or None."""
        self._ensure_loaded()
        return self._cache.get(preset_id)

    def build_role_resources(self, preset_ids: List[str]) -> Dict[str, str]:
        """Build merged {path: content} dict from selected presets.

        All products use the same OpenClaw-style split:
        body sections → SOUL.md + AGENTS.md, frontmatter → IDENTITY.md.
        When multiple presets are selected, same-name files are concatenated.
        """
        self._ensure_loaded()
        merged: Dict[str, str] = {}

        for pid in preset_ids:
            entry = self._cache.get(pid)
            if not entry:
                continue
            files = _split_body_for_openclaw(entry["meta"], entry["body"])
            for path, content in files.items():
                if path in merged:
                    merged[path] += "\n" + content
                else:
                    merged[path] = content

        return merged
