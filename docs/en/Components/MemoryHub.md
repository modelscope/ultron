---
slug: MemoryHub
title: Memory Hub
description: "Ultron Memory Hub: unified ingestion, storage, and clustering"
---

# Memory Hub

Memory Hub is Ultron's unified entry point for the memory layer. It brings together three sub-services and works with the **trajectory layer (Trajectory Hub)**: `.jsonl` sessions can land in the trajectory table first, then be **task-segmented** and metric-scored before reaching memory (see [Trajectory Hub](TrajectoryHub.md)).

| Sub-service | Responsibility |
|-------------|----------------|
| **Ingestion Service** | ETL: conversation `.jsonl` via `ingest(paths)` → LLM task segmentation → task_segments (fingerprint dedup); **`ingest_text`** (no file path) → main LLM extracts memories directly |
| **Memory Service** | Core engine: deduplication, tiers, semantic retrieval, redaction |
| **Knowledge Cluster** | Semantic clustering of related memories as input for skill crystallization |

Data flow (overview):

```
Raw input (session .jsonl paths or plain text for ingest_text)
    │
    ▼
Ingestion Service
 ├─ Session .jsonl (ingest(paths)) → LLM task segmentation → task_segments (fingerprint dedup)
 │       → scheduled job: ms-agent trajectory metrics → eligible segments → upload_memory
 └─ ingest_text (plain text, no file path) → LLM structured extraction → direct upload
    │
    ▼
Memory Service — dedup, embedding, storage, tiering
    │
    ▼
Knowledge Cluster — semantic similarity; feeds Skill Hub crystallization
```

---

## Ingestion Service

There are **two** ingestion entry points; do not confuse them:

**`ingest(paths)` (path list: conversation `.jsonl` files, or directories containing multiple `.jsonl` files)**

The typical format is **conversation `.jsonl`**: one JSON object per line with `role` and `content`. You can pass multiple files and directories; directories are expanded recursively and **only `.jsonl` files are collected** (other extensions are skipped). For each file, the system first stores session metadata, then runs **LLM task segmentation** to split the conversation into independent task segments and uses **content fingerprints** for incremental deduplication into **`task_segments`**. The main LLM does **not** extract memories during this request; trajectory metric analysis and `upload_memory` run in the background job at segment granularity. To ingest ordinary plain text as memories, use **`ingest_text`** below.

**`ingest_text(text)` (a single string)**

**Always** uses the main LLM to extract text and `upload_memory` directly; it does **not** write `trajectory_records` and does **not** go through the trajectory quality pipeline, regardless of prior `ingest` or `.jsonl` uploads.

If you construct `IngestionService` yourself, you **must** inject **`trajectory_service`** for `.jsonl`; otherwise ingestion fails.

### Core capabilities

| Capability | Description |
|------------|-------------|
| **Unified ingest** | Single `ingest(paths)` entry; primary path is session `.jsonl` → LLM task segmentation → task_segments |
| **Text ingest** | `ingest_text` takes a string only; main LLM uploads memories, no trajectory table |
| **Task segmentation** | `.jsonl` files are automatically split into independent task segments, metric-scored and extracted per segment |
| **Fingerprint dedup** | Content fingerprint (SHA-256) for incremental tracking, avoiding duplicate processing |
| **Sessions / trajectories** | `.jsonl` goes to task_segments and the trajectory metrics pipeline; `trajectory_service` required |
| **Directory expansion** | Directories recurse and collect **`.jsonl` only** (skips hidden path segments and symlinks) |
| **Type detection** | Memory type inferred automatically |
| **Dedup** | Merges with existing memories automatically |
| **Raw archive** | When a database exists, archiving is always on: one `ingest_file` row per `.jsonl` from `ingest(paths)`; one `ingest_text` row per standalone `ingest_text` |

### Examples

```python
from ultron import Ultron

ultron = Ultron()

# Unified ingest: session exports (multiple files or dirs; conversation .jsonl)
result = ultron.ingest(
    paths=["/path/to/sessions/run-20250419.jsonl", "/path/to/sessions/"],
    agent_id="my-agent",
)

print(f"Files processed: {result['total_files']}")
print(f"Total memories: {result['total_memories']}")
```

When **only `.jsonl`** land in trajectories, `total_memories` counts **new segment rows** (`new_segments`); memories are written later by the scheduled job.

```python
# Text ingest (no file path: direct extraction, no trajectory table)
result = ultron.ingest_text(
    text="""
    Investigation:
    1. pip install failed inside Docker
    2. Error: Could not find a version that satisfies...
    3. Cause: container has no outbound network
    4. Fix: configure a proxy or use --network host
    """,
)

for mem in result.get("memories", []):
    print(f"[{mem['memory_type']}] {mem['content'][:50]}...")
```

### Dispatch flow

```
Input path list
    ↓
Recursively expand directories
    ↓
Per file: archive raw bytes to raw_user_uploads
 (skip files over 10 MB; archive failure does not block ingestion)
    ↓
Each `.jsonl` file
    → LLM task segmentation → independent task segments (fingerprint dedup)
    → Also writes trajectory_records as session metadata
    ↓
Memory Service (dedup, promotion); metric-eligible segments upload via scheduled job
    ↓
Knowledge Cluster (semantic clustering)
    ↓
Aggregate results
```

### Incremental sessions and task segmentation

**`.jsonl`**: the server runs **LLM task segmentation** on each file, splitting the conversation into independent task segments. Each segment has a **SHA-256 content fingerprint** (16 hex chars). When re-uploading the same file:
- Fingerprint matches → skip (idempotent)
- Fingerprint does not match → archive old segment's memories (precise tag-based archival), re-process

Files at different paths are treated as different sessions — **no cross-file deduplication**. See [Trajectory Hub](TrajectoryHub.md).

### Scheduled job and tier rebalance

The background `run_decay_loop` in `ultron/services/background.py` (started from `server.py` lifespan) runs **before** tier rebalance, in order: **task segmentation** → **segment metric labeling** → **extract memories from eligible segments** (`TrajectoryMemoryExtractor`) → `run_tier_rebalance` → skill evolution → consolidation (if enabled). Therefore memories originating from `.jsonl` may appear one `decay_interval_hours` cycle later than the ingest request.

### LLM extraction

Default model `qwen3.6-flash`. Extracts reusable experience such as:

- Errors and resolutions
- Security-related items
- Patterns and regularities
- Shareable life experience (non-private)

Output shape:

```json
{
  "memories": [
    {
      "content": "Error / problem description",
      "context": "Where it happened",
      "resolution": "Fix",
      "confidence": 0.85,
      "tags": ["python", "docker"]
    }
  ]
}
```

### Token management

| Setting | Purpose |
|---------|---------|
| `llm_max_input_tokens` | Maximum input tokens |
| `llm_prompt_reserve_tokens` | Tokens reserved for the model reply |

Long content is truncated or split automatically.

---

## Memory Service

Core storage engine for multi-agent shared memory: upload, deduplication, percentile tier reassignment, and semantic retrieval.

### Tier

| Tier | Description | Behavior |
|------|-------------|----------|
| **HOT** | High hit rate (top N%) | Available to all agents immediately |
| **WARM** | Medium hit rate (next M%) | Returned when context matches |
| **COLD** | Low hit rate (remainder) | Still searched by default, ranked lower (tier boost 0.8 plus time decay) |

Tiers are reassigned in bulk by **`run_tier_rebalance`** on interval `decay_interval_hours`, in the **same** background loop **after** trajectory labeling and uploading memories from good trajectories:

1. Sort all active memories by `hit_count` DESC, then `last_hit_at` DESC
2. Top `hot_percentile`% (default 10%) → HOT
3. Next `warm_percentile`% (default 40%) → WARM
4. Remainder → COLD
5. COLD memories older than `cold_ttl_days` are marked `archived` (not deleted, but excluded from search and tier rebalance)

`hit_count` is driven by three adoption signals:

| Signal | Weight | Description |
|--------|--------|-------------|
| Details (full fetch) | +2 | Agent explicitly chose full text |
| Search (appears in results) | +1 | Retrieved in search |
| Merge (dedup merge) | +1 | Similar memory merged on upload |

### Status

| Status | Description |
|--------|-------------|
| `active` | Default for all live memories |
| `archived` | After COLD TTL; excluded from search and tier rebalance |

### MemoryType

Determined by the server LLM automatically; **callers cannot set the type**:

| Type | Description |
|------|-------------|
| `error` | Error experience (engineering, tooling, etc.) |
| `security` | Security events |
| `correction` | Corrections |
| `pattern` | Observed patterns |
| `preference` | Explicit preferences |
| `life` | Shareable everyday facts (e.g. flight seat tips) |

### Examples

```python
from ultron import Ultron

ultron = Ultron()

# Upload memory (type decided by the server)
record = ultron.upload_memory(
    content="ModuleNotFoundError: No module named 'pandas'",
    context="Running data analysis script inside a Docker container",
    resolution="pip install pandas",
    tags=["python", "docker", "pandas"],
)

print(f"Memory id: {record.id}")
print(f"Type: {record.memory_type}")
print(f"Tier: {record.tier}")
print(f"Status: {record.status}")
```

```python
# Semantic search
results = ultron.search_memories(
    query="Python import error",
    detail_level="l1",
    limit=10,
)

for r in results:
    print(f"[{r.record.memory_type}] {r.record.content[:50]}...")
    print(f"  Similarity: {r.similarity_score:.4f}")
```

```python
# Full text by id
details = ultron.get_memory_details(["id1", "id2", "id3"])
```

### Upload and near-duplicate merge

Entry point: `MemoryService.upload_memory`; completion when a near duplicate matches: **`_complete_near_duplicate_upload`**.

**Scan scope**: Within the same **`memory_type`**, search HOT, WARM, and COLD embeddings for near duplicates.

**Rule**: Cosine similarity **greater than** `dedup_similarity_threshold` (default 0.85) counts as the same memory.

**On hit**:

1. Logging + stats: `increment_memory_hit`; original text stored in **`memory_contributions`**
2. Merge body: LLM semantic merge; if LLM is unavailable or the call fails, **skip the merge** (keep original text unchanged) and retry on the next duplicate upload when the LLM recovers
3. Write back: if body text changed → recompute embedding and regenerate L0/L1; if only tags changed → update tags only

**On miss**: New MemoryRecord (WARM, `active`).

### L0 / L1 / full context levels

| Level | Content | Use |
|-------|---------|-----|
| `l0` | One-line summary (`summary_l0`); body-like fields cleared | Quick scan, lowest token use |
| `l1` | Core overview (`summary_l0` + `overview_l1`) | Narrow candidates before details |
| `full` | Full original content | Fetch by id via `get_memory_details` |

Semantic search supports `l0` and `l1` only; load full text in a second step with `get_memory_details`.

### Time decay

```
hotness = exp(-decay_alpha * days_since_last_hit)
```

Decay affects retrieval ranking (weight from `time_decay_weight`); it does not change tier by itself. Tiers come only from **`run_tier_rebalance`** percentiles on `hit_count`.

### Data redaction

On upload, `content`, `context`, and `resolution` are redacted before persistence.

Based on **[Microsoft Presidio](https://github.com/microsoft/presidio)** (spaCy backend, Chinese and English). Additional regex rules:

| Kind | Replacement tag |
|------|-----------------|
| Email, phone, IP, person names, etc. | Presidio default labels |
| OpenAI / LLM API keys | `<LLM_API_KEY>` |
| GitHub token | `<GITHUB_TOKEN>` |
| AWS access key | `<AWS_ACCESS_KEY>` |
| Bearer / Basic auth headers | `<REDACTED_TOKEN>` |
| Generic credential-like fields | `<REDACTED_CREDENTIAL>` |
| UUID | `<UUID>` |
| China mobile numbers | `<PHONE_NUMBER>` |
| Unix/Windows user paths | `<USER>` / `<PATH>` |

---

## Knowledge Cluster

Automatically groups semantically related memories into clusters. Clusters are the raw material for skill crystallization in Skill Hub: when a cluster holds enough memories, Skill Hub’s evolution engine crystallizes them into a structured skill.

### How it works

After each memory upload, assign it to the nearest cluster by embedding cosine similarity (threshold ≥ `cluster_similarity_threshold`, default 0.75), or create a new cluster. Centroids update as members change.

```
New memory uploaded
    ↓
Cosine similarity vs all cluster centroids
    ↓
├─ Best similarity ≥ 0.75 → join cluster, update centroid
└─ All clusters < 0.75     → create new cluster
```

### Collaboration with Skill Hub

Knowledge Cluster does “grouping”; Skill Hub’s evolution engine does “crystallization”:

| Phase | Owner | Trigger |
|-------|-------|---------|
| Memory clustering | Memory Hub (Knowledge Cluster) | Each memory upload |
| Crystallization readiness | Memory Hub (Knowledge Cluster) | Memories in cluster ≥ `crystallization_threshold` (default 5) |
| Skill crystallization | Skill Hub (Evolution Engine) | Read ready clusters; LLM synthesizes skill |
| Re-crystallization readiness | Memory Hub (Knowledge Cluster) | Crystallized cluster gains ≥ `recrystallization_delta` (default 3) new memories |
| Skill re-crystallization | Skill Hub (Evolution Engine) | Read all memories in cluster; re-synthesize |

### API

| Method | Description |
|--------|-------------|
| `assign_memory_to_cluster(memory)` | Assign a memory to a cluster |
| `get_clusters_ready_to_crystallize()` | Clusters at critical mass but not yet crystallized |
| `get_clusters_ready_to_recrystallize()` | Crystallized clusters with enough new memories |
| `get_cluster_memories(cluster_id)` | All memories in a cluster |
| `run_initial_clustering()` | One-shot clustering for all existing memories |

### Data model

```python
KnowledgeCluster:
    cluster_id: str          # UUID
    topic: str               # LLM-generated topic label
    memory_ids: List[str]    # Memories in this cluster
    centroid: List[float]    # Cluster centroid embedding
    skill_slug: Optional[str]       # Crystallized skill (written back by Skill Hub)
    superseded_slugs: List[str]     # Older skills superseded by merge
```

### Configuration

| Environment variable | Default | Description |
|---------------------|---------|-------------|
| `ULTRON_CLUSTER_SIMILARITY_THRESHOLD` | `0.75` | Similarity threshold for joining a cluster |
| `ULTRON_CRYSTALLIZATION_THRESHOLD` | `5` | Minimum memories to crystallize |
| `ULTRON_RECRYSTALLIZATION_DELTA` | `3` | New memories that trigger re-crystallization |

---

## HTTP API

### Ingestion

```
POST /ingest
{"paths": ["/path/to/sessions/run.jsonl", "/path/to/sessions/"], "agent_id": "my-agent"}

POST /ingest/text
{"text": "Raw text content..."}
```

### Memory

```
POST /memories/upload
{"content": "...", "context": "...", "resolution": "...", "tags": [...]}

POST /memories/search
{"query": "...", "detail_level": "l1", "limit": 10}

POST /memories/details
{"ids": ["id1", "id2"]}
```

## Dependencies

1. **DashScope API key**: environment variable `DASHSCOPE_API_KEY`
2. **LLM availability**: default `qwen3.6-flash` for non-jsonl ingestion extraction (e.g. `ingest_text`), memory merge, etc.; task segmentation and the trajectory metric model use configured LLM services; see [Configuration](Config.md) and [Trajectory Hub](TrajectoryHub.md)
3. **Embedding service**: used for semantic retrieval and clustering

If the main LLM is unavailable, non-jsonl ingestion may fail or be limited. If the trajectory metric model is unavailable, segment metric analysis is **skipped** and segments stay unlabeled until it recovers.
