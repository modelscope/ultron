---
slug: SDK
title: Python SDK
description: Ultron Python client reference
---

# Python SDK

Use Ultron directly from Python without running the HTTP server.

## Install

```shell
pip install -e .
```

## Quick start

```python
from ultron import Ultron

ultron = Ultron()

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

## Memory

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

Semantic search across memory types.

```python
results = ultron.search_memories(
    query: str,
    tier: str = None,       # None=all, or "hot"/"warm"/"cold"/"all"
    limit: int = None,      # None -> UltronConfig.memory_search_default_limit (ULTRON_MEMORY_SEARCH_LIMIT)
    detail_level: str = "l0",  # "l0" or "l1"
) -> List[MemorySearchResult]
```

### get_memory_details

Fetch full records by id.

```python
records = ultron.get_memory_details(
    memory_ids: List[str],
) -> List[MemoryRecord]
```

### get_memory_stats

```python
stats = ultron.get_memory_stats() -> dict
```

---

## Smart ingestion

### ingest

Routes `.jsonl` to incremental session extract; other files to LLM extract. Accepts files and directories.

```python
result = ultron.ingest(
    paths: List[str],
) -> dict
```

### ingest_text

```python
result = ultron.ingest_text(
    text: str,
) -> dict
```

---

## Skill generation

### generate_skill_from_memory

```python
skill = ultron.generate_skill_from_memory(
    memory_id: str,
) -> Optional[Skill]
```

### auto_generate_skills

```python
skills = ultron.auto_generate_skills(
    limit: int = None,  # None -> UltronConfig.skill_auto_detect_batch_limit (ULTRON_SKILL_AUTO_DETECT_LIMIT)
) -> List[Skill]
```

---

## Tier rebalance

### run_tier_rebalance

Reassigns HOT/WARM/COLD by `hit_count` percentiles, archives expired COLD, triggers skills for new HOT rows.

```python
summary = ultron.run_tier_rebalance() -> dict
```

### run_memory_decay

Alias of `run_tier_rebalance` (backward compatible).

```python
summary = ultron.run_memory_decay() -> dict
```

---

## Raw uploads archive (`raw_user_uploads`)

When `archive_raw_uploads` is on: `ingest(paths)` writes one row per file (`ingest_file`); **standalone** `ingest_text` / HTTP text ingest without `source_file` writes UTF-8 text (`ingest_text`); **file-backed** LLM extract does not duplicate decoded text. `upload_skill` writes each pack file (`skill_upload_file`).

### get_raw_user_upload

```python
upload = ultron.get_raw_user_upload(
    upload_id: str,
) -> Optional[dict]
```

### list_raw_user_uploads

```python
uploads = ultron.list_raw_user_uploads(
    limit: int = 100,
    offset: int = 0,
    source_prefix: str = None,
) -> List[dict]
```

---

## Skills

### search_skills

Semantic search over internal skills and ModelScope catalog entries. Each hit includes `source` (`"internal"` or `"catalog"`) and `full_name`.

```python
results = ultron.search_skills(
    query: str,
    limit: int = None,  # None -> UltronConfig.skill_search_default_limit (ULTRON_SKILL_SEARCH_LIMIT)
) -> List[RetrievalResult]
```

### upload_skills

```python
result = ultron.upload_skills(
    paths: List[str],
) -> dict
```

**Example:**

```python
result = ultron.upload_skills(paths=["/path/to/my-skill"])
result = ultron.upload_skills(paths=["/path/to/skills-folder"])
```

### install_skill_to

```python
result = ultron.install_skill_to(
    full_name: str,
    target_dir: str,
) -> dict
```

**Example:**

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

### list_all_skills

```python
skills = ultron.list_all_skills() -> List[dict]
```

---

## Harness Hub

### list_agents

```python
agents = ultron.list_agents(user_id: str) -> List[dict]
```

### remove_agent

```python
ok = ultron.remove_agent(user_id: str, agent_id: str) -> bool
```

### harness_sync_up

```python
profile = ultron.harness_sync_up(
    user_id: str,
    agent_id: str,
    product: str,
    resources: dict,
) -> dict
```

### harness_sync_down

```python
profile = ultron.harness_sync_down(
    user_id: str,
    agent_id: str,
) -> Optional[dict]
```

### get_harness_profile

```python
profile = ultron.get_harness_profile(
    user_id: str,
    agent_id: str,
) -> Optional[dict]
```

### create_harness_share

```python
share = ultron.create_harness_share(
    user_id: str,
    agent_id: str,
    visibility: str = "link",
) -> dict
```

### import_harness_share

```python
profile = ultron.import_harness_share(
    token: str,
    target_user_id: str,
    target_agent_id: str,
) -> dict
```

### list_harness_shares

```python
shares = ultron.list_harness_shares(user_id: str) -> List[dict]
```

### delete_harness_share

```python
ok = ultron.delete_harness_share(token: str) -> bool
```

---

## Stats

### get_stats

```python
stats = ultron.get_stats() -> dict
```

---

## Admin

### reset_all

Wipes the database and skill files.

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

```python
from ultron import (
    Ultron,
    UltronConfig,
    default_config,
    Skill,
    SkillMeta,
    SkillFrontmatter,
    SkillUsageRecord,
    SkillStatus,
    SourceType,
    Complexity,
    MemoryRecord,
    MemoryTier,
    MemoryType,
    MemoryStatus,
    RetrievalQuery,
    RetrievalResult,
    MemorySearchResult,
    IntentAnalyzer,
    ConversationExtractor,
    LLMService,
    LLMOrchestrator,
    SmartIngestionService,
)
```
