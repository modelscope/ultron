---
slug: SkillHub
title: Skill Hub
description: "Ultron Skill Hub: storage, retrieval, and evolution in one place"
---

# Skill Hub

Skill Hub is Ultron’s structured knowledge base for reusable skills, whether crystallized from memory or uploaded by agents. It supports semantic search, automatic taxonomy, and self-evolution.

Skill Hub integrates two subsystems:

| Subsystem | Responsibility |
|-----------|----------------|
| **Skill management** | Storage, search, taxonomy, upload, installation |
| **Skill evolution** | Crystallize skills from knowledge clusters; re-crystallize continuously as new knowledge arrives |

---

## Core concepts

### Skill structure

Each skill consists of:

| Part | File | Description |
|------|------|-------------|
| Metadata | `_meta.json` | Owner, version, publish time, etc. |
| Body | `SKILL.md` | YAML front matter + Markdown body |
| Scripts | `scripts/` | Optional helper scripts |

### Skill source

| Value | Description |
|-------|-------------|
| `evolution` | Crystallized or re-crystallized from a knowledge cluster |
| `catalog` | Synced with the ModelScope Skill Hub catalog |

## Examples

### Search skills

```python
from ultron import Ultron

ultron = Ultron()

results = ultron.search_skills(
    query="how to fix Python import errors",
    limit=5,
)

for r in results:
    print(f"Skill: {r.skill.name}")
    print(f"  Description: {r.skill.description}")
    print(f"  Similarity: {r.similarity_score:.4f}")
```

### Upload skills

```python
# Upload from a directory (must contain SKILL.md + _meta.json)
result = ultron.upload_skills(
    paths=["/path/to/my-skill-dir"],
)

# Batch: scan immediate subdirectories under the parent that contain SKILL.md
result = ultron.upload_skills(
    paths=["/path/to/skills-folder"],
)
```

## Skill directory layout

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

## SKILL.md format

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
    source_type: evolution
---

# Python import errors

## Problem description

When you see `ModuleNotFoundError`...

## Steps

1. Check the module is installed
2. ...

## Example

```python
# Example code
```
```

## Relationship to memory

Reusable skills come mainly from **knowledge-cluster evolution** (`evolution`): multiple related memories are clustered first, then the evolution engine creates or updates the corresponding skill. ModelScope catalog skills use **`catalog`** and are independent of the memory pipeline.

---

## Skill self-evolution

### Design philosophy

Skill Hub is a repository service: it does not execute skills or observe runtime behavior. Evolution signals must therefore come only from data Ultron can observe: how fast memory accumulates, how embeddings cluster semantically, and how an LLM scores structural quality.

That leads to a core design choice: **skills are not hand-written or one-shot; they crystallize from collective experience**. When enough related memories occupy the same semantic region, they point to a reusable workflow pattern — the prototype of a skill. As new experience keeps arriving, skills “re-crystallize,” but each evolution must **strictly improve** structural quality versus the previous version, or the new version is not published and the old one is kept.

This balances two risks:

- **Premature crystallization**: too few memories produce unrepresentative skills, hallucinations, or overfitting to a single case
- **Unbounded drift**: rewriting on every new memory would destroy already validated content

### Three-stage pipeline

Evolution is split into three stages, owned by different components:

| Stage | Trigger | Owner | Core behavior |
|-------|---------|-------|---------------|
| **Knowledge clustering** | Each new memory is stored | `KnowledgeClusterService` | Assign memories to the nearest cluster by embedding cosine similarity (threshold 0.75), or create a cluster; centroid is the mean of member embeddings and updates as members change |
| **Crystallization** | Cluster has ≥5 memories and no linked skill yet | `SkillEvolutionEngine` | LLM synthesizes a multi-step workflow skill from all memories; after quality gates and provenance verification, persisted as v1.0 |
| **Re-crystallization** | Crystallized cluster gains ≥3 new memories | `SkillEvolutionEngine` | Uses current skill as skeleton, re-synthesizes with all memories; new structure score must be strictly higher than the old to publish |

Clustering is the “perception layer”: pure embedding similarity, no LLM, can run on every memory write. Crystallization and re-crystallization are the “synthesis layer”: multiple LLM calls, run in background batches.

### Crystallization

Crystallization creates a skill from scratch. The trigger is critical mass in the cluster (default ≥5 memories): a single memory is one event; five or more similar memories reveal a cross-scenario pattern.

The LLM must synthesize a **multi-step workflow skill**, not a simple summary: trigger (when to use), step sequence (≥3 steps with clear inputs/outputs), edge handling (common failures and fallbacks), and branches (different paths for different cases).

If memories are too scattered to form a coherent workflow, the LLM returns `quality: insufficient` and no skill is created. This “active refusal” avoids forcing low-quality skills.

### Re-crystallization

Re-crystallization uses the **current skill as a skeleton**, not a full rewrite. The LLM is instructed to prefer targeted edits over wholesale rewrites and to keep existing content unless substantive new knowledge warrants change.

Rationale: (1) crystallized skills already passed quality gates and provenance checks; a full rewrite throws that away. (2) Targeted edits are easier for the upgrade gate to judge: real value raises the structure score; noise does not, and the gate rejects publication.

If new memories add no real value, the LLM returns `evolution: unnecessary` and the pipeline stops before verification.

### Two quality gates

#### Quality gate (`_meets_quality_bar`)

A lightweight heuristic before LLM verification to filter obviously bad outputs and save verification calls.

| Check | How | Notes |
|-------|-----|-------|
| Minimum length | Token count ≥150 (character count ÷3 when no LLM) | Hard fail if not met |
| Step structure | Regex for numbering/lists/headings, ≥3 items | Ensures substantive steps |
| Trigger | Keywords (when/trigger/适用/触发, etc.) | Ensures usage context is stated |
| Edge handling | Keywords (error/fail/异常/回退, etc.) | Ensures failures are covered |

Rule: minimum length must pass, and **at least two** of the last three checks must pass.

#### Provenance verification (`verify_skill`)

A **separate LLM** from the synthesis model runs verification to avoid self-grading bias. For each step/claim it assigns a provenance label:

| Label | Meaning |
|-------|---------|
| `grounded` | Supported by source memories |
| `hallucinated` | No evidence in sources |
| `contradicted` | Conflicts with source memories |

Pass condition: `grounded_in_evidence ≥ 0.8` and `has_contradiction = false`.

LLM synthesis can hallucinate plausible steps with no memory support. Provenance verification anchors the skill in real experience so it is distilled experience, not pure generation.

### Structure score and upgrade gate

After verification, a **structure score** is computed for version comparison:

| Dimension | Weight | Meaning |
|-----------|--------|---------|
| `workflow_clarity` | 0.35 | Steps are clear, ordered, executable |
| `specificity_and_reusability` | 0.35 | Instructions are concrete and reusable, not vague |
| `preserves_existing_value` | 0.30 | On re-crystallization: retains valuable content from the previous version |

**Structure score** = 0.35 × workflow_clarity + 0.35 × specificity_and_reusability + 0.30 × preserves_existing_value

**Upgrade gate**: on re-crystallization, the new score must be **strictly greater** than the old score to publish. Otherwise record `revert` and keep the old version.

This addresses a core problem: how to prevent “evolution” that is actually regression. Asking an LLM “is this better?” is unreliable (longer often reads “better”). Structure score gives a comparable, auditable signal and traceable history.

### Evolution records

Each crystallization, re-crystallization, or rejection writes an `EvolutionRecord`:

```python
EvolutionRecord:
    skill_slug: str          # Skill identifier
    cluster_id: str          # Source cluster
    old_version: str         # Previous version (None on first crystallization)
    new_version: str         # New version (empty if rejected)
    old_score: float         # Previous structure score
    new_score: float         # New structure score
    status: str              # crystallized | recrystallized | revert | constraint_failed
    trigger: str             # initial_clustering | new_memory | manual | background
    memory_count: int        # Memories in the synthesis batch
    mutation_summary: str    # Summary of this change
```

`revert` means the upgrade gate rejected the candidate; `constraint_failed` means provenance verification failed. Full history is available via `GET /skills/evolution-history`.

### Background execution

Evolution does not use a separate timer. `run_evolution_cycle()` runs on the same cadence as `run_decay_loop` in `ultron/services/background.py` (right after tier rebalance), with interval `decay_interval_hours`. Each cycle has two phases sharing one batch cap (default 3):

| Phase | Workload | Priority |
|-------|----------|----------|
| Phase one | Clusters ready to crystallize (critical mass, no skill yet) | First |
| Phase two | Clusters ready to re-crystallize (new memories past delta) | Remaining quota |

Phase one first: crystallization creates value from nothing; re-crystallization is incremental and can wait.

---

## External catalog (ModelScope Skill Hub)

Ultron can search the ModelScope Skill Hub catalog (**80,364** skills), merged with internal skills and sorted by similarity.

### Unified search

`search_skills` returns both internal and catalog rows, sorted by similarity. Each row includes:

| Field | Description |
|-------|-------------|
| `source` | `"internal"` or `"catalog"` |
| `full_name` | Catalog full name, e.g. `@ns/skill-name` |

### Install skills

`install_skill_to` handles both sources: resolve an internal skill by slug first; otherwise install from ModelScope via `modelscope skills add`.

```python
# Internal skill (by slug)
result = ultron.install_skill_to(
    full_name="ultron",
    target_dir="~/.nanobot/workspace/skills",
)
# result: {"success": true, "source": "internal", "installed_path": "..."}

# ModelScope catalog skill
result = ultron.install_skill_to(
    full_name="@anthropics/minimax-pdf",
    target_dir="~/.nanobot/workspace/skills",
)
# result: {"success": true, "source": "catalog", "installed_path": "..."}
```

---

## HTTP API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/skills/search` | POST | Semantic skill search (internal + catalog in one response) |
| `/skills/upload` | POST | Upload skill packs |
| `/skills/install` | POST | Install a skill into a target directory |
| `/skills/clusters` | GET | List clusters and their status |
| `/skills/evolution-history` | GET | Evolution history (crystallize / re-crystallize / reject) |

---

## Configuration

| Environment variable | Default | Description |
|---------------------|---------|-------------|
| `ULTRON_EVOLUTION_ENABLED` | `true` | Enable evolution |
| `ULTRON_EVOLUTION_BATCH_LIMIT` | `3` | Max clusters processed per evolution cycle |
| `ULTRON_CLUSTER_SIMILARITY_THRESHOLD` | `0.75` | Cosine threshold for assigning a memory to a cluster |
| `ULTRON_CRYSTALLIZATION_THRESHOLD` | `5` | Minimum memories to trigger crystallization |
| `ULTRON_RECRYSTALLIZATION_DELTA` | `3` | New memories required to trigger re-crystallization |
