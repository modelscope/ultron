# Copyright (c) ModelScope Contributors. All rights reserved.
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .models import Skill, SkillMeta


class SkillStorage:
    """
    Filesystem layout for skills: ``{skills_dir}/{slug}-{version}/`` with
    ``SKILL.md``, ``_meta.json``, and optional ``scripts/``.
    """

    def __init__(self, skills_dir: str, archive_dir: str):
        self.skills_dir = Path(skills_dir)
        self.archive_dir = Path(archive_dir)
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def _get_skill_dir(self, slug: str, version: str) -> Path:
        return self.skills_dir / f"{slug}-{version}"

    def save_skill(self, skill: Skill) -> str:
        """
        Persist ``skill`` to disk.

        Returns:
            Absolute path to the skill directory.
        """
        skill_dir = self._get_skill_dir(skill.meta.slug, skill.meta.version)
        skill_dir.mkdir(parents=True, exist_ok=True)

        skill_md_path = skill_dir / "SKILL.md"
        skill_md_path.write_text(self._build_skill_md(skill), encoding="utf-8")

        meta_path = skill_dir / "_meta.json"
        meta_path.write_text(skill.meta.to_json(), encoding="utf-8")

        if skill.scripts:
            scripts_dir = skill_dir / "scripts"
            scripts_dir.mkdir(parents=True, exist_ok=True)
            for script_name, script_content in skill.scripts.items():
                script_path = scripts_dir / script_name
                script_path.write_text(script_content, encoding="utf-8")

        return str(skill_dir)

    def _build_skill_md(self, skill: Skill) -> str:
        metadata_str = json.dumps(skill.frontmatter.metadata, ensure_ascii=False)
        frontmatter = f"""---
name: {skill.frontmatter.name}
description: {skill.frontmatter.description}
metadata: {metadata_str}
---

"""
        return frontmatter + skill.content

    def load_skill(self, slug: str, version: str) -> Optional[Skill]:
        """
        Load from ``{slug}-{version}`` under ``skills_dir``.

        Returns:
            ``Skill`` or ``None`` if the directory or ``SKILL.md`` is missing.
        """
        skill_dir = self._get_skill_dir(slug, version)
        if not skill_dir.exists():
            return None

        return self.load_skill_from_dir(str(skill_dir))

    def load_skill_from_dir(self, skill_dir: str) -> Optional[Skill]:
        """
        Parse a directory that contains ``SKILL.md`` (and optionally ``_meta.json``).

        Returns:
            ``Skill`` or ``None`` if paths are invalid or parsing fails.
        """
        from ..utils.skill_parser import SkillParser

        skill_path = Path(skill_dir)
        if not skill_path.exists():
            return None

        skill_md_path = skill_path / "SKILL.md"
        if not skill_md_path.exists():
            return None

        skill_md_content = skill_md_path.read_text(encoding="utf-8")

        parser = SkillParser()
        frontmatter, content = parser.parse_skill_md(skill_md_content)
        if frontmatter is None:
            return None

        meta_path = skill_path / "_meta.json"
        if meta_path.exists():
            meta_dict = json.loads(meta_path.read_text(encoding="utf-8"))
            meta = SkillMeta.from_dict(meta_dict)
        else:
            meta = SkillMeta(
                owner_id="unknown",
                slug=frontmatter.name,
                version="1.0.0",
                published_at=int(datetime.now().timestamp() * 1000),
            )

        scripts = {}
        scripts_dir = skill_path / "scripts"
        if scripts_dir.exists():
            for script_file in scripts_dir.iterdir():
                if script_file.is_file():
                    scripts[script_file.name] = script_file.read_text(encoding="utf-8")

        return Skill(
            meta=meta,
            frontmatter=frontmatter,
            content=content,
            scripts=scripts,
            local_path=str(skill_path),
        )

    def skill_exists(self, slug: str, version: str) -> bool:
        skill_dir = self._get_skill_dir(slug, version)
        return skill_dir.exists() and (skill_dir / "SKILL.md").exists()

    def read_skill_md_text(self, slug: str, version: Optional[str] = None) -> Optional[str]:
        """
        Return raw ``SKILL.md`` text for ``slug`` (latest on disk when ``version`` is omitted).
        """
        if version is None:
            version = self.get_latest_version(slug)
            if not version:
                return None
        path = self._get_skill_dir(slug, version) / "SKILL.md"
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    def get_skill_versions(self, slug: str) -> List[str]:
        versions = []
        for item in self.skills_dir.iterdir():
            if item.is_dir() and item.name.startswith(f"{slug}-"):
                version = item.name[len(slug) + 1:]
                if version:
                    versions.append(version)
        return sorted(versions, reverse=True)

    def get_latest_version(self, slug: str) -> Optional[str]:
        versions = self.get_skill_versions(slug)
        return versions[0] if versions else None

    def delete_skill(self, slug: str, version: str) -> bool:
        skill_dir = self._get_skill_dir(slug, version)
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
            return True
        return False

    def archive_skill(self, slug: str, version: str) -> Optional[str]:
        """
        Move ``{slug}-{version}`` from ``skills_dir`` to ``archive_dir``.

        Returns:
            Path to the archive directory, or ``None`` if the skill was missing.
        """
        skill_dir = self._get_skill_dir(slug, version)
        if not skill_dir.exists():
            return None

        archive_path = self.archive_dir / f"{slug}-{version}"
        if archive_path.exists():
            shutil.rmtree(archive_path)

        shutil.move(str(skill_dir), str(archive_path))
        return str(archive_path)

    def restore_skill(self, slug: str, version: str) -> Optional[str]:
        """
        Move a package from ``archive_dir`` back into ``skills_dir``.

        Returns:
            Restored skill directory path, or ``None`` if the archive is missing.
        """
        archive_path = self.archive_dir / f"{slug}-{version}"
        if not archive_path.exists():
            return None

        skill_dir = self._get_skill_dir(slug, version)
        if skill_dir.exists():
            shutil.rmtree(skill_dir)

        shutil.move(str(archive_path), str(skill_dir))
        return str(skill_dir)

    def copy_skill_to_target(self, slug: str, version: str, target_dir: str) -> Optional[str]:
        """
        Clone ``{slug}-{version}`` into ``target_dir/{slug}-{version}``.

        Returns:
            Destination path, or ``None`` if the source skill is missing.
        """
        skill_dir = self._get_skill_dir(slug, version)
        if not skill_dir.exists():
            return None

        target_path = Path(target_dir) / f"{slug}-{version}"
        if target_path.exists():
            shutil.rmtree(target_path)

        shutil.copytree(str(skill_dir), str(target_path))
        return str(target_path)

    def list_all_skills(self) -> List[Dict[str, str]]:
        """
        Scan ``skills_dir`` for directories containing ``SKILL.md``.

        Directory names are parsed as ``slug-version`` when the segment after the
        last hyphen looks like a version (leading digit); otherwise the whole name
        is treated as slug with version ``1.0.0``.
        """
        skills = []
        for item in self.skills_dir.iterdir():
            if item.is_dir() and (item / "SKILL.md").exists():
                name = item.name
                parts = name.rsplit("-", 1)
                if len(parts) == 2:
                    slug, version = parts
                    if version and version[0].isdigit():
                        skills.append({
                            "slug": slug,
                            "version": version,
                            "path": str(item),
                        })
                    else:
                        skills.append({
                            "slug": name,
                            "version": "1.0.0",
                            "path": str(item),
                        })
                else:
                    skills.append({
                        "slug": name,
                        "version": "1.0.0",
                        "path": str(item),
                    })
        return skills

    def get_storage_stats(self) -> Dict:
        total_size = 0

        for item in self.skills_dir.rglob("*"):
            if item.is_file():
                total_size += item.stat().st_size

        skills_list = self.list_all_skills()
        total_skills = len(skills_list)

        archived_skills = 0
        for item in self.archive_dir.iterdir():
            if item.is_dir():
                archived_skills += 1

        return {
            "total_skills": total_skills,
            "archived_skills": archived_skills,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "skills_dir": str(self.skills_dir),
            "archive_dir": str(self.archive_dir),
        }

    def clear_all_skill_files(self, *, include_archive: bool = True) -> dict:
        """
        Remove every skill subdirectory under ``skills_dir``, and optionally wipe
        ``archive_dir``. Used with a DB wipe for full reset.
        """
        removed_skills = 0
        removed_archive = 0
        if self.skills_dir.exists():
            for item in list(self.skills_dir.iterdir()):
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                    removed_skills += 1
        if include_archive and self.archive_dir.exists():
            for item in list(self.archive_dir.iterdir()):
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                    removed_archive += 1
                elif item.is_file():
                    try:
                        item.unlink()
                        removed_archive += 1
                    except OSError:
                        pass
        self._ensure_directories()
        return {
            "removed_skill_dirs": removed_skills,
            "removed_archive_entries": removed_archive,
        }
