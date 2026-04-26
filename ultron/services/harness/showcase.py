# Copyright (c) ModelScope Contributors. All rights reserved.
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SHOWCASE_BY_LANG = {
    "zh": _REPO_ROOT / "docs" / "zh" / "Showcase",
    "en": _REPO_ROOT / "docs" / "en" / "Showcase",
}


def _parse_frontmatter(text: str) -> tuple:
    """Return (metadata_dict, body_str)."""
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
            if val.startswith("[") and val.endswith("]"):
                val = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
            meta[key.strip()] = val
    return meta, parts[2].lstrip("\n")


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class ShowcaseService:
    """Loads showcase Markdown from docs/zh/Showcase/ and docs/en/Showcase/.

    Each locale directory holds ``{slug}.md``.
    """

    def __init__(self, showcase_dirs: Optional[Dict[str, Path]] = None):
        self._dirs = showcase_dirs or dict(_SHOWCASE_BY_LANG)
        self._cache: Dict[str, dict] = {}  # key: "slug:lang"
        self._slugs: set = set()
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            self.load()

    def _parse_file(self, md_file: Path) -> Optional[dict]:
        raw = md_file.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(raw)
        if not meta.get("name"):
            return None
        return {
            "name": meta["name"],
            "description": meta.get("description", ""),
            "emoji": meta.get("emoji", ""),
            "short_code": meta.get("short_code", ""),
            "agent_id": meta.get("agent_id", ""),
            "tags": meta.get("tags", []),
            "body": body,
        }

    def _load_locale_dir(self, lang: str, dir_path: Path) -> int:
        if not dir_path.is_dir():
            return 0
        count = 0
        for md_file in sorted(dir_path.glob("*.md")):
            stem = md_file.stem
            if stem.endswith(".en"):
                slug = stem[:-3]
                file_lang = "en"
            else:
                slug = stem
                file_lang = lang
            entry = self._parse_file(md_file)
            if not entry:
                continue
            entry["slug"] = slug
            self._cache[f"{slug}:{file_lang}"] = entry
            self._slugs.add(slug)
            count += 1
        return count

    def load(self):
        self._cache.clear()
        self._slugs.clear()
        loaded_any = False
        for lang, dir_path in sorted(self._dirs.items()):
            n = self._load_locale_dir(lang, dir_path)
            if n:
                loaded_any = True
                logger.debug("Showcase loaded %d files from %s", n, dir_path)
        if not loaded_any:
            logger.warning("No showcase files under docs/zh/Showcase or docs/en/Showcase")
        self._loaded = True
        if not self._cache:
            logger.warning("No showcase content loaded (check docs/zh/Showcase or docs/en/Showcase)")
        else:
            logger.info("Showcase entries: %d (unique slugs: %d)", len(self._cache), len(self._slugs))

    def list_showcases(self, lang: str = "zh") -> List[dict]:
        self._ensure_loaded()
        result = []
        for slug in sorted(self._slugs):
            entry = self._cache.get(f"{slug}:{lang}") or self._cache.get(f"{slug}:zh")
            if entry:
                result.append({k: v for k, v in entry.items() if k != "body"})
        return result

    def get_showcase(self, slug: str, lang: str = "zh") -> Optional[dict]:
        self._ensure_loaded()
        return self._cache.get(f"{slug}:{lang}") or self._cache.get(f"{slug}:zh")
