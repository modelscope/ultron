# Copyright (c) ModelScope Contributors. All rights reserved.
import json
import logging
import re
from typing import Any, Optional, Tuple

from ..core.models import SkillFrontmatter

logger = logging.getLogger(__name__)


class SkillParser:
    """
    Parse and build ``SKILL.md`` bodies: YAML front matter (minimal parser, no PyYAML)
    plus trailing markdown content.
    """

    FRONTMATTER_PATTERN = re.compile(
        r'^---\s*\n(.*?)\n---\s*\n',
        re.DOTALL,
    )

    def parse_skill_md(self, content: str) -> Tuple[Optional[SkillFrontmatter], str]:
        """
        Split ``content`` into front matter and markdown body.

        Returns:
            ``(frontmatter, body)``; ``frontmatter`` is ``None`` when the file has no
            leading ``---`` block or parsing fails (body is then the original string).
        """
        match = self.FRONTMATTER_PATTERN.match(content)
        if not match:
            return None, content

        frontmatter_text = match.group(1)
        markdown_content = content[match.end():]

        try:
            frontmatter = self._parse_frontmatter(frontmatter_text)
            return frontmatter, markdown_content.strip()
        except Exception as e:
            logger.warning("Failed to parse frontmatter: %s", e)
            return None, content

    def _parse_frontmatter(self, text: str) -> SkillFrontmatter:
        """Parse a ``---`` inner block into ``name``, ``description``, and ``metadata``."""
        lines = text.strip().split('\n')
        data = {}
        current_key = None
        current_value_lines = []

        for line in lines:
            if ':' in line and not line.startswith(' ') and not line.startswith('\t'):
                if current_key:
                    data[current_key] = self._parse_yaml_value('\n'.join(current_value_lines))

                key, _, value = line.partition(':')
                current_key = key.strip()
                current_value_lines = [value.strip()] if value.strip() else []
            elif current_key:
                current_value_lines.append(line)

        if current_key:
            data[current_key] = self._parse_yaml_value('\n'.join(current_value_lines))

        name = data.get('name', '')
        description = data.get('description', '')
        metadata = data.get('metadata', {})

        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}

        return SkillFrontmatter(
            name=name,
            description=description,
            metadata=metadata,
        )

    def _parse_yaml_value(self, value: str) -> Any:
        """Best-effort scalar / JSON literal parsing for front matter values."""
        value = value.strip()

        if not value:
            return ''

        if value.startswith('{') or value.startswith('['):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass

        if value.lower() == 'true':
            return True
        if value.lower() == 'false':
            return False

        if value.lower() in ('null', 'none', '~'):
            return None

        try:
            if '.' in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            return value[1:-1]

        return value

    def build_skill_md(
        self,
        name: str,
        description: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """Serialize ``name``, ``description``, ``metadata``, and markdown ``content`` into SKILL.md text."""
        if metadata is None:
            metadata = {}

        if 'ultron' not in metadata:
            metadata['ultron'] = {
                'categories': ['general'],
                'complexity': 'medium',
            }

        if 'openclaw' not in metadata:
            metadata['openclaw'] = {
                'emoji': '🔧',
            }

        metadata_json = json.dumps(metadata, ensure_ascii=False)

        frontmatter = f"""---
name: {name}
description: {description}
metadata: {metadata_json}
---

"""
        return frontmatter + content

    def _slugify(self, text: str) -> str:
        """Normalize ``text`` to a slug (latin + CJK allowed)."""
        slug = text.lower()
        slug = re.sub(r'[\s\-_]+', '-', slug)
        slug = re.sub(r'[^a-z0-9\-\u4e00-\u9fff]', '', slug)
        slug = slug.strip('-')
        return slug or 'unknown'