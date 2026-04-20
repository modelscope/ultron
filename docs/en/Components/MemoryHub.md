---
slug: MemoryHub
title: Memory Hub
description: "Ultron Memory Hub: unified ingestion, storage, and clustering"
---

# Memory Hub

Memory Hub is Ultron’s unified entry point for the memory layer. It integrates three sub-services:

| Sub-service | Responsibility |
|-------------|----------------|
| **Smart Ingestion** | ETL pipeline: files / text → structured memories |
| **Memory Service** | Core storage engine: deduplication, tiers, semantic retrieval, redaction |
| **Knowledge Cluster** | Semantic clustering: groups related memories as input for skill crystallization in Skill Hub |

Data flow:

```
Raw content (files / text / sessions)
    │
    ▼
Smart Ingestion — LLM extracts structured memories
    │
    ▼
Memory Service — dedup, embedding, storage, tier management
    │
    ▼
Knowledge Cluster — cluster by semantic similarity; feeds Skill Hub crystallization
```

---

## Smart Ingestion

Unified knowledge-extraction pipeline. Pass file or directory paths, or raw text; routing is automatic by type: `.jsonl` uses ConversationExtractor (incremental); everything else uses LLM text extraction.

### Core capabilities

| Capability | Description |
|------------|-------------|
| **Unified ingest** | Single `ingest(paths)` entry; routing by file extension |
| **Text ingest** | Raw text directly |
| **Session extract** | `.jsonl` files use incremental extraction automatically |
| **Directory expansion** | Directory paths recurse into all regular files (skips hidden path segments and symlinks) |
| **Type detection** | Memory type inferred automatically |
| **Dedup** | Merges with existing memories automatically |
| **Raw archive** | When `archive_raw_uploads` is enabled: `ingest(paths)` records one `ingest_file` row per file; plain `ingest_text` (not read from a file) records one `ingest_text` row; when text is read from a file then extracted, only file bytes are archived, not duplicate decoded body text |

### Examples

```python
from ultron import Ultron

ultron = Ultron()

# Unified ingest (mixed paths: regular files + .jsonl + directories)
result = ultron.ingest(
    paths=["/path/to/debug_log.txt", "/path/to/sessions/"],
)

print(f"Files processed: {result['total_files']}")
print(f"Total memories: {result['total_memories']}")
```

```python
# Text ingest
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
Recursively expand files under directories
    ↓
For each file: archive raw bytes to raw_user_uploads
 (skip files over 10 MB; archive failure does not block ingestion)
    ↓
Route by extension
 ├─ .jsonl → ConversationExtractor (incremental)
 └─ other  → LLM text extraction
    ↓
Upload to Memory Service (dedup, tier promotion)
    ↓
Assign to Knowledge Cluster (semantic clustering)
    ↓
Aggregate results
```

### Incremental session handling

1. The server tracks the last processed line count per file path
2. Each run processes only new lines
3. `session_extract_overlap_lines` can prepend prior lines for continuity before new content

### LLM extraction

Default model: `qwen3.6-flash`. It extracts reusable experience such as:

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
| `conversation_extract_window_tokens` | Session chunk window size |

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

Tiers are reassigned in bulk by **`run_tier_rebalance`** (background task on interval `decay_interval_hours`):

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
2. Merge body: LLM merge if `llm_service` is available; otherwise rule merge (keep longer substring, else join with `---`)
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
{"paths": ["/path/to/file.txt", "/path/to/sessions/"]}

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
2. **LLM available**: default `qwen3.6-flash` (ingestion extraction and memory merge)
3. **Embedding service**: used for semantic retrieval and clustering

If the LLM is unavailable, ingestion falls back to rule-based memory-type inference, and merge falls back to rule-based concatenation.
