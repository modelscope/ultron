# Copyright (c) ModelScope Contributors. All rights reserved.
import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ...core.models import Skill, SkillStatus
from ...services.skill import RetrievalQuery, RetrievalResult

logger = logging.getLogger(__name__)


class SkillMixin:
    def generate_skill_from_memory(
        self,
        memory_id: str,
    ) -> Optional[Skill]:
        """Build a skill from a memory row that reached the HOT tier."""
        return self.skill_generator.generate_skill_from_memory(
            memory_id=memory_id,
        )

    def auto_generate_skills(self, limit: Optional[int] = None) -> List[Skill]:
        """
        Detect high-frequency memories and generate skills automatically.

        When ``limit`` is omitted, uses ``config.skill_auto_detect_batch_limit`` (``ULTRON_SKILL_AUTO_DETECT_LIMIT``).
        """
        return self.skill_generator.auto_detect_and_generate(limit=limit)

    def upload_skill(
        self,
        skill_dir: str,
    ) -> Optional[Skill]:
        """Upload a new skill package from a directory tree."""
        root = Path(skill_dir)
        if root.is_dir():
            self._archive_skill_tree(str(skill_dir))

        skill = self.storage.load_skill_from_dir(skill_dir)
        if not skill:
            logger.warning("Failed to load skill from '%s'", skill_dir)
            return None

        skill.meta.owner_id = "ultron-system"
        skill.meta.published_at = int(datetime.now().timestamp() * 1000)
        skill.meta.status = SkillStatus.ACTIVE

        _cats = skill.categories
        if not _cats or _cats == ["general"]:
            suggested = self.catalog.suggest_categories(
                skill.content or "",
                skill.description or "",
                name=skill.name or "",
            )
            skill.frontmatter.metadata.setdefault("ultron", {})
            skill.frontmatter.metadata["ultron"]["categories"] = suggested

        existing = self.db.get_skill(skill.meta.slug)
        if existing and existing.get("version") == skill.meta.version:
            skill.meta.version = self._increment_version(skill.meta.version)

        embedding = self.embedding.embed_skill(
            skill.name,
            skill.description,
            skill.content,
        )
        skill.meta.embedding = embedding

        local_path = self.storage.save_skill(skill)
        skill.local_path = local_path

        self.db.save_skill(skill.meta, skill.frontmatter, local_path)

        return skill

    def upload_skills(
        self,
        paths: List[str],
    ) -> dict:
        """
        Upload skills from filesystem paths.

        For each path: if it contains SKILL.md, treat as a single skill directory
        and call upload_skill. Otherwise if it's a directory, scan immediate
        subdirectories for those containing SKILL.md and upload each.
        """
        results = []
        for p in paths:
            root = Path(p)
            if not root.exists():
                results.append({"path": p, "success": False, "error": "path not found"})
                continue
            if (root / "SKILL.md").exists():
                skill = self.upload_skill(str(root))
                if skill:
                    results.append(
                        {
                            "path": p,
                            "success": True,
                            "slug": skill.meta.slug,
                            "version": skill.meta.version,
                            "name": skill.name,
                        }
                    )
                else:
                    results.append(
                        {"path": p, "success": False, "error": "failed to load skill"}
                    )
            elif root.is_dir():
                for sub in sorted(root.iterdir()):
                    if sub.is_dir() and (sub / "SKILL.md").exists():
                        skill = self.upload_skill(str(sub))
                        if skill:
                            results.append(
                                {
                                    "path": str(sub),
                                    "success": True,
                                    "slug": skill.meta.slug,
                                    "version": skill.meta.version,
                                    "name": skill.name,
                                }
                            )
                        else:
                            results.append(
                                {
                                    "path": str(sub),
                                    "success": False,
                                    "error": "failed to load skill",
                                }
                            )
            else:
                results.append(
                    {
                        "path": p,
                        "success": False,
                        "error": "not a skill directory (no SKILL.md)",
                    }
                )

        successful = sum(1 for r in results if r.get("success"))
        return {"total": len(results), "successful": successful, "results": results}

    def get_skill(self, slug: str, version: Optional[str] = None) -> Optional[Skill]:
        """Load a ``Skill`` by slug; uses latest version when ``version`` is omitted."""
        if version is None:
            version = self.storage.get_latest_version(slug)
            if not version:
                return None
        return self.storage.load_skill(slug, version)

    def get_internal_skill_md_text(self, slug: str) -> Optional[str]:
        """Raw ``SKILL.md`` for a published internal skill (DB row + filesystem)."""
        row = self.db.get_skill(slug)
        if not row:
            return None
        lp = (row.get("local_path") or "").strip()
        if lp:
            p = Path(lp) / "SKILL.md"
            if p.is_file():
                return p.read_text(encoding="utf-8")
        ver = row.get("version")
        if ver:
            text = self.storage.read_skill_md_text(slug, ver)
            if text is not None:
                return text
        return self.storage.read_skill_md_text(slug, None)

    def search_skills(
        self,
        query: str,
        limit: Optional[int] = None,
    ) -> List[RetrievalResult]:
        """
        Semantic search over published skills.

        When ``limit`` is omitted, uses ``config.skill_search_default_limit`` (``ULTRON_SKILL_SEARCH_LIMIT``).
        """
        retrieval_query = RetrievalQuery(
            query_text=query,
            limit=limit,
        )
        return self.retriever.search_skills(retrieval_query)

    def install_skill_to(self, full_name: str, target_dir: str) -> dict:
        """
        Install a skill to target_dir.

        Checks internal Ultron skills first (by slug). If not found internally,
        falls back to ``modelscope skills add <full_name>``.
        """
        name = full_name.rsplit("/", 1)[-1] if "/" in full_name else full_name
        target = Path(target_dir).expanduser() / name

        version = self.storage.get_latest_version(name)
        if version:
            skill = self.storage.load_skill(name, version)
            if skill and skill.local_path and Path(skill.local_path).exists():
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(skill.local_path, str(target), dirs_exist_ok=True)
                except Exception as e:
                    return {"success": False, "error": f"Copy failed: {e}"}
                return {
                    "success": True,
                    "full_name": full_name,
                    "source": "internal",
                    "installed_path": str(target),
                }

        modelscope_dir = Path.home() / ".agents" / "skills" / name
        try:
            result = subprocess.run(
                ["modelscope", "skills", "add", full_name],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"modelscope skills add failed: {result.stderr.strip()}",
                }
        except FileNotFoundError:
            return {"success": False, "error": "modelscope CLI not found"}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "modelscope skills add timed out"}

        if not modelscope_dir.exists():
            return {
                "success": False,
                "error": f"Skill not found after install: {modelscope_dir}",
            }

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(str(modelscope_dir), str(target), dirs_exist_ok=True)
        except Exception as e:
            return {"success": False, "error": f"Copy failed: {e}"}

        return {
            "success": True,
            "full_name": full_name,
            "source": "catalog",
            "installed_path": str(target),
        }
