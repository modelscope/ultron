---
slug: SkillHub
title: Skill Hub
description: Structured skills, search, catalog, and installation
---

# Skill Hub

Skill Hub is Ultron’s structured knowledge base for skills crystallized from memory or uploaded by agents, with semantic search and automatic taxonomy.

## Concepts

### Layout

| Part | File | Description |
|------|------|-------------|
| Metadata | `_meta.json` | Owner, version, published time, status, embedding |
| Body | `SKILL.md` | YAML front matter + Markdown |
| Scripts | `scripts/` | Optional helpers |

### Status

| Status | Meaning |
|--------|---------|
| `active` | Usable |
| `archived` | Archived |

### Source

| Source | Meaning |
|--------|---------|
| `memory_crystallization` | Auto-generated from high-frequency memory |
| `error_learning` | From error-type memory |
| `security_learning` | From security memory |
| `generation` | Generic generation fallback |
| `catalog` | From ModelScope Skill Hub catalog |

## Examples

### Search

```python
from ultron import Ultron

ultron = Ultron()

results = ultron.search_skills(
    query="how to fix Python import errors",
    limit=5,
)

for r in results:
    print(r.skill.name, r.skill.description, r.similarity_score)
```

### Upload

```python
result = ultron.upload_skills(paths=["/path/to/my-skill-dir"])

result = ultron.upload_skills(paths=["/path/to/skills-folder"])
```

## On-disk layout

```
~/.ultron/skills/
├── python-import-error-1.0.0/
│   ├── _meta.json
│   ├── SKILL.md
│   └── scripts/
│       └── check_imports.py
├── docker-debugging-1.0.0/
│   ├── _meta.json
│   └── SKILL.md
└── ...
```

## SKILL.md shape

```markdown
---
name: python-import-error
description: Fix Python module import errors
metadata:
  ultron:
    categories:
      - debugging
      - python
    complexity: low
    source_type: error_learning
---

# Python import errors

## Problem

When you see `ModuleNotFoundError`...

## Steps

1. Check the module is installed
2. ...

## Example

Use a short Python snippet in the body, or attach scripts under `scripts/`.
```

## Relationship to memory

| Memory | → | Skill |
|--------|---|-------|
| Concrete error case | Crystallize | Reusable procedure |
| Enters HOT | → | Structured doc |

Auto batch generation (`auto_detect_and_generate`) candidates (see `get_promotion_candidates`):

- Memory in HOT
- No linked skill yet (`generated_skill_slug` empty)

Ordered by `hit_count`, freshness, etc. When `limit` is omitted, batch size uses `UltronConfig.skill_auto_detect_batch_limit` (`ULTRON_SKILL_AUTO_DETECT_LIMIT`).

## External catalog (ModelScope Skill Hub)

Ultron searches the ModelScope Skill Hub catalog together with internal skills, merged and sorted by similarity.

### Import catalog

```bash
python scripts/import_skill_catalog.py --catalog skills.json --batch-size 20 --sleep 0.3
```

Flags: `--catalog`, `--batch-size`, `--sleep`, `--skip-existing`.

### Unified search

`search_skills` returns both internal and catalog rows:

| Field | Meaning |
|-------|---------|
| `source` | `"internal"` or `"catalog"` |
| `full_name` | Catalog full name, e.g. `@ns/skill-name` |

### Install

`install_skill_to` resolves internal slug first, otherwise runs `modelscope skill add` for catalog skills.

```python
result = ultron.install_skill_to(
    full_name="ultron",
    target_dir="~/.nanobot/workspace/skills",
)

result = ultron.install_skill_to(
    full_name="@anthropics/minimax-pdf",
    target_dir="~/.nanobot/workspace/skills",
)
```
