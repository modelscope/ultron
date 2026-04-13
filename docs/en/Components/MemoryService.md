---
slug: MemoryService
title: Memory service
description: Remote shared memory: tiers, dedup, search, sanitization
---

# Memory service

MemoryService is Ultron’s core component for multi-agent shared memory: upload, deduplication, percentile tier rebalance, semantic search, and more.

## Concepts

### Tier

| Tier | Meaning | Behavior |
|------|---------|----------|
| **HOT** | Top N% by hits | Immediately useful across agents |
| **WARM** | Next M% by hits | Returned when context matches |
| **COLD** | Remaining | Still searchable, lower rank (tier boost 0.8 plus time decay) |

Tiers are reassigned in bulk by **`run_tier_rebalance`** (background on `decay_interval_hours`):

1. Sort active memories by `hit_count` DESC, then `last_hit_at` DESC
2. Top `hot_percentile`% (default 10%) → HOT
3. Next `warm_percentile`% (default 40%) → WARM
4. Rest → COLD
5. Memories newly entering HOT trigger skill generation (`_try_auto_generate_skill`)
6. COLD memories older than `cold_ttl_days` → `archived` (excluded from search and rebalance)

`hit_count` is driven by three signals:

| Signal | Weight | Meaning |
|--------|--------|---------|
| Details (full fetch) | +2 | Agent chose to load full text |
| Search (hit in results) | +1 | Retrieved in search |
| Merge (dedup) | +1 | Merged from similar upload |

### Status

| Status | Meaning |
|--------|---------|
| `active` | Default for live memories |
| `archived` | Past COLD TTL; excluded from search and rebalance |

### MemoryType

Assigned by the server LLM; **callers cannot set the type**. One of:

| Type | Meaning |
|------|---------|
| `error` | Engineering/tooling errors |
| `security` | Security incidents |
| `correction` | Corrections |
| `pattern` | Observed patterns |
| `preference` | Explicit preferences |
| `life` | Shareable everyday tips (e.g. travel seating) |

## Examples

### Upload

```python
from ultron import Ultron

ultron = Ultron()

record = ultron.upload_memory(
    content="ModuleNotFoundError: No module named 'pandas'",
    context="Running data analysis inside Docker",
    resolution="pip install pandas",
    tags=["python", "docker", "pandas"],
)

print(record.id, record.memory_type, record.tier, record.status)
```

### Search

```python
results = ultron.search_memories(
    query="Python module import error",
    detail_level="l1",
    limit=10,
)

for r in results:
    print(r.record.memory_type, r.record.content[:50], r.similarity_score)
```

### Full text

```python
details = ultron.get_memory_details(["id1", "id2", "id3"])
```

## Upload and near-duplicate merge (`upload_memory`)

Entry point: `MemoryService.upload_memory`; merge completion: **`_complete_near_duplicate_upload`**.

**Scan scope**: Within the same **`memory_type`**, search HOT, WARM, and COLD embeddings for near duplicates.

**Rule**: Cosine similarity **greater than** `dedup_similarity_threshold` (default 0.85) → same logical memory.

**On hit**:

1. Log (`upload_memory.dedup_hit`, etc.)
2. `increment_memory_hit`; original text recorded in **`memory_contributions`**
3. Merge body: `_merge_memory_fields` → if `llm_service` present, try **`LLMService.merge_memories`** (fields capped by `memory_merge_max_field_tokens`), else rule merge **`_merge_pair_fields`** (substring keeps longer text, else blocks joined with `---`), then `_cap_merge_field_by_tokens`
4. **Persist**:
   - If **content/context/resolution** changed vs stored: recompute embedding, regenerate L0/L1 (`_generate_summaries`), **`update_memory_merged_body`** (including merged `tags`)
   - If only **tags** changed: **`update_memory_merged_body`** updates tags only; keep embedding and summaries

**On miss**: New **`MemoryRecord`** (WARM, `active`), `save_memory_record`; log `upload_memory.created`.

## L0 / L1 / full

Each memory has three granularities for token-efficient retrieval:

| Level | Content | Use |
|-------|---------|-----|
| `l0` | One-line `summary_l0`; body fields cleared | Cheapest scan |
| `l1` | `summary_l0` + `overview_l1` | Shortlist before details |
| `full` | Raw `content`, `context`, `resolution` | Via `get_memory_details` by id |

`search_memories` supports `l0` and `l1` only; always use `get_memory_details` for full text.

```python
results_l0 = ultron.search_memories(query, detail_level="l0")
selected_ids = [r.record.id for r in results_l0[:3]]
full_records = ultron.get_memory_details(selected_ids)
```

## Time decay

```
hotness = exp(-decay_alpha * days_since_last_hit)
```

Decay affects ranking (`time_decay_weight`), not tier. Tiers come only from `run_tier_rebalance` percentiles on `hit_count`.

## Data model

Aligned with `ultron.core.models.MemoryRecord`: `id`, `memory_type`, `content`, `context`, `resolution`, `tier`, `status`, `hit_count`, `tags`, `embedding`, `summary_l0`, `overview_l1`, `generated_skill_slug`, `created_at`, `last_hit_at`, etc.

## Sanitization

Before persistence, `content`, `context`, and `resolution` are redacted.

Based on **[Microsoft Presidio](https://github.com/microsoft/presidio)** with spaCy (`en_core_web_sm` / `zh_core_web_sm`). Language is inferred from CJK ratio.

Additional regex coverage:

| Kind | Replacement tag |
|------|-----------------|
| Email, phone, IP, person, … | Presidio labels (e.g. `<EMAIL_ADDRESS>`, `<PERSON>`) |
| OpenAI / LLM API keys | `<LLM_API_KEY>` |
| GitHub token | `<GITHUB_TOKEN>` |
| AWS access key | `<AWS_ACCESS_KEY>` |
| Bearer / Basic headers | `<REDACTED_TOKEN>` |
| Credential-like fields (`password=`, …) | `<REDACTED_CREDENTIAL>` |
| UUID | `<UUID>` |
| China mobile numbers | `<PHONE_NUMBER>` |
| Unix/Windows user paths | `<USER>` / `<PATH>` |

Implemented in `DataSanitizer` (`utils/sanitizer.py`); MemoryService applies it automatically.
