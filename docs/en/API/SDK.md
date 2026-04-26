---
slug: SDK
title: Python SDK
description: Ultron Python SDK reference
---

# Python SDK

Ultron ships a Python SDK so you can use it directly from code without running the HTTP server.

## Install

```shell
pip install -e .
```

## Quick start

```python
from ultron import Ultron

# Default configuration
ultron = Ultron()

# Or custom configuration
from ultron import UltronConfig

config = UltronConfig(
    data_dir="~/.my-ultron",
    llm_provider="openai",
    llm_model="gpt-5",
    llm_base_url="https://api.openai.com/v1",
    llm_api_key="your-api-key",
)
ultron = Ultron(config=config)
```

---

## Memory management

### upload_memory

```python
record = ultron.upload_memory(
    content: str,
    context: str,
    resolution: str,
    tags: List[str] = None,
) -> MemoryRecord
```

**Example:**

```python
record = ultron.upload_memory(
    content="ModuleNotFoundError: No module named 'pandas'",
    context="Running inside Docker",
    resolution="pip install pandas",
    tags=["python", "docker"],
)
```

### search_memories

Semantic search over memories.

```python
results = ultron.search_memories(
    query: str,
    tier: str = None,       # None = all tiers, or "hot"/"warm"/"cold"/"all"
    limit: int = None,      # None -> UltronConfig.memory_search_default_limit (ULTRON_MEMORY_SEARCH_LIMIT)
    detail_level: str = "l0",  # "l0" or "l1"
) -> List[MemorySearchResult]
```

### get_memory_details

Fetch full memory rows by id list.

```python
records = ultron.get_memory_details(
    memory_ids: List[str],
) -> List[MemoryRecord]
```

### get_memory_stats

Return memory statistics.

```python
stats = ultron.get_memory_stats() -> dict
```

---

## Smart ingestion

### ingest

Unified ingestion: routes by file type automatically. Accepts a mix of files and directories.

- **`.jsonl` (default `Ultron`)**: The system first stores session metadata, then runs **LLM task segmentation** to split conversations into independent task segments and uses **content fingerprints** for incremental deduplication into `task_segments`. The background job stores trajectory metrics per segment, then uploads memories only from metric-eligible segments. The main LLM does **not** extract memories during `ingest`. Pass **`agent_id`** so incremental progress is tracked per session file.
- **Other files**: LLM text extraction, then direct upload to the memory store.

```python
result = ultron.ingest(
    paths: List[str],
    agent_id: str = "",
) -> dict
```

For trajectory statistics and **SFT export**, use `ultron.trajectory_service`. `export_sft()` exports **segmented independent task segments** (each segment is a complete multi-turn conversation), filterable by `task_type` and `min_quality_score` (defaults to `trajectory_sft_score_threshold`, same **0–1** scale as `summary.overall_score` in `quality_metrics`). E.g. `get_trajectory_stats()`, `export_sft(task_type=..., min_quality_score=0.8, limit=...)`. See [Trajectory Hub](../Components/TrajectoryHub.md).

### ingest_text

Ingest raw text.

```python
result = ultron.ingest_text(
    text: str,
) -> dict
```

---

## Tier rebalance

### run_tier_rebalance

Reassign HOT/WARM/COLD by `hit_count` percentiles and archive expired COLD memories.

```python
summary = ultron.run_tier_rebalance() -> dict
```

## Raw uploads archive (`raw_user_uploads`)

Raw archive (always when DB exists): `ingest(paths)` writes one row per ingested `.jsonl` (`ingest_file`); **`ingest_text`** / HTTP plain-text ingest (no `source_file`) writes one UTF-8 row (`ingest_text`). `upload_skill` writes one row per file in the pack (`skill_upload_file`).

### get_raw_user_upload

Load an archive row by id (includes decoded fields such as `payload_text` / `payload_base64`).

```python
upload = ultron.get_raw_user_upload(
    upload_id: str,
) -> Optional[dict]
```

### list_raw_user_uploads

List archive summaries (without full payload bodies).

```python
uploads = ultron.list_raw_user_uploads(
    limit: int = 100,
    offset: int = 0,
    source_prefix: str = None,
) -> List[dict]
```

---

## Skill management

### search_skills

Semantic search over skills (internal skills and ModelScope Skill Hub catalog entries, merged and sorted by similarity). Each hit includes `source` (`"internal"` or `"catalog"`) and `full_name`.

```python
results = ultron.search_skills(
    query: str,
    limit: int = None,  # None -> UltronConfig.skill_search_default_limit (ULTRON_SKILL_SEARCH_LIMIT)
) -> List[RetrievalResult]
```

### upload_skills

Batch upload: pass a list of directory paths; scans immediate subdirectories that contain `SKILL.md` and uploads each.

```python
result = ultron.upload_skills(
    paths: List[str],
) -> dict
```

**Example:**

```python
# Single skill directory
result = ultron.upload_skills(
    paths=["/path/to/my-skill"],
)

# All skills under a folder
result = ultron.upload_skills(
    paths=["/path/to/skills-folder"],
)
# result: {"total": 3, "successful": 3, "results": [...]}
```

### install_skill_to

Install a skill into a target directory. Resolves internal Ultron skills first; otherwise installs from ModelScope Skill Hub via `modelscope skill add`.

```python
result = ultron.install_skill_to(
    full_name: str,    # Skill name or full path (e.g. "@ns/name"); internal skills use slug directly
    target_dir: str,   # Destination directory (caller-defined)
) -> dict
```

**Example:**

```python
# Internal skill
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

### upload_skill

Upload a single skill directory.

```python
skill = ultron.upload_skill(
    skill_dir: str,
) -> Optional[Skill]
```

### get_skill

Load a skill by slug; optionally pin a version.

```python
skill = ultron.get_skill(
    slug: str,
    version: Optional[str] = None,
) -> Optional[Skill]
```

### get_internal_skill_md_text

Get the raw SKILL.md text for an internal skill.

```python
text = ultron.get_internal_skill_md_text(
    slug: str,
) -> Optional[str]
```

### list_all_skills

List all skills.

```python
skills = ultron.list_all_skills() -> List[dict]
```

### Skill evolution and clusters

For **server operators**: crystallization and re-crystallization run in the same cadence as the background `run_decay_loop` in `ultron/services/background.py` (trajectory, tier rebalance, etc.); there is **no** public HTTP API. In the **same process** as `Ultron` with the same `data_dir` / database, troubleshoot or inspect via the SQLite `Database` on `ultron.db`:

```python
clusters = ultron.db.get_all_clusters()
rows = ultron.db.get_evolution_history("my-skill-slug", limit=20)
```

To run one evolution cycle from a standalone script, build `SkillEvolutionEngine` with an `UltronConfig` that points at the same data directory and call `run_evolution_cycle()`; see `ultron.services.skill.skill_evolution`.

---

## Harness Hub (personal sync)

### list_agents

List all agents for a user.

```python
agents = ultron.list_agents(user_id: str) -> List[dict]
```

### remove_agent

Remove an agent (cascade-deletes profile and shares).

```python
ok = ultron.remove_agent(user_id: str, agent_id: str) -> bool
```

### harness_sync_up

Upload a workspace bundle to the server.

```python
profile = ultron.harness_sync_up(
    user_id: str,
    agent_id: str,
    product: str,
    resources: dict,        # {relative path: file content}
) -> dict
```

### harness_sync_down

Download a workspace bundle.

```python
profile = ultron.harness_sync_down(
    user_id: str,
    agent_id: str,
) -> Optional[dict]
```

### get_harness_profile

Get the profile for a (user, agent) pair.

```python
profile = ultron.get_harness_profile(
    user_id: str,
    agent_id: str,
) -> Optional[dict]
```

### get_profiles_by_user

List all workspace profiles for that user.

```python
profiles = ultron.get_profiles_by_user(user_id: str) -> list
```

### create_harness_share

Create a share token from the current profile (raises if no profile; call `harness_sync_up` first). If a share already exists for the same agent, the token is reused and the snapshot is refreshed.

```python
share = ultron.create_harness_share(
    user_id: str,
    agent_id: str,
    visibility: str = "public",
) -> dict
```

### list_harness_shares

List all shares created by the user.

```python
shares = ultron.list_harness_shares(user_id: str) -> List[dict]
```

### delete_harness_share

Delete a share token.

```python
ok = ultron.delete_harness_share(token: str) -> bool
```

---

## Stats

### get_stats

Aggregates skill storage, category stats, embedding model info, and memory stats (same shape as HTTP `GET /stats`).

```python
stats = ultron.get_stats() -> dict
```

---

## Admin

### reset_all

Reset all data (clear database, delete skill files).

```python
result = ultron.reset_all() -> dict
```

---

## Data models

### MemoryRecord

```python
@dataclass
class MemoryRecord:
    id: str
    memory_type: str
    content: str
    context: str
    resolution: str
    summary_l0: str
    overview_l1: str
    tier: str
    status: str
    scope: str
    hit_count: int
    tags: List[str]
    created_at: datetime
    last_hit_at: datetime
```

### MemorySearchResult

```python
@dataclass
class MemorySearchResult:
    record: MemoryRecord
    similarity_score: float
    tier_boosted_score: float
```

### Skill

```python
@dataclass
class Skill:
    meta: SkillMeta
    frontmatter: SkillFrontmatter
    content: str
    scripts: Dict[str, str]
    local_path: Optional[str]
```

### RetrievalResult

```python
@dataclass
class RetrievalResult:
    skill: Skill
    similarity_score: float
    combined_score: float
```

---

## Public exports

The SDK re-exports:

```python
from ultron import (
    # Main entry
    Ultron,

    # Configuration
    UltronConfig,
    default_config,
    load_ultron_dotenv,

    # Models — skills
    Skill,
    SkillMeta,
    SkillFrontmatter,
    SkillUsageRecord,
    SourceType,
    Complexity,

    # Models — memory
    MemoryRecord,
    MemoryTier,
    MemoryType,
    MemoryStatus,

    # Retrieval
    RetrievalQuery,
    RetrievalResult,
    MemorySearchResult,

    # Services
    IntentAnalyzer,
    LLMService,
    LLMOrchestrator,
    IngestionService,
)
```
