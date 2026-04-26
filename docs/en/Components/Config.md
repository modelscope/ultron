---
slug: Config
title: Configuration
description: UltronConfig, environment variables, and field reference
---

# Configuration

Ultron uses the `UltronConfig` dataclass for configuration. **`ULTRON_*` environment variables** supply defaults for each field; explicit arguments to `UltronConfig(...)` **override** the environment. The LLM uses an OpenAI-compatible surface (`llm_provider`, `llm_model`, `llm_base_url`, `llm_api_key`). Embeddings are selected by `embedding_backend` (`dashscope` or `local`); `dashscope_api_key` can share `DASHSCOPE_API_KEY` with the LLM and is written to `os.environ` on `Ultron(...)` init when set. `llm_api_key` resolves in order: `ULTRON_API_KEY` → `ULTRON_LLM_API_KEY` → `OPENAI_API_KEY` → `DASHSCOPE_API_KEY`.

On first import of `ultron.config` (or `import ultron`), `load_ultron_dotenv()` reads key/value pairs from `~/.ultron/.env` into `os.environ` (`override=False`).

- The repo provides **`.env.example`**; you can copy `ULTRON_*` values into **`~/.ultron/.env`** (create the directory if needed).
- Without **`python-dotenv`**, `load_ultron_dotenv()` is a no-op; use exported variables or your process manager instead.

## Configure in code

```python
from ultron import Ultron, UltronConfig

config = UltronConfig(
    data_dir="~/.ultron",
    embedding_model="text-embedding-v4",
    llm_model="qwen3.6-flash",
    dedup_similarity_threshold=0.85,
)

ultron = Ultron(config=config)
```

## Field reference

### Data storage

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `data_dir` | str | `~/.ultron` | Root data directory |
| `db_name` | str | `ultron.db` | SQLite database filename |

### DashScope credentials

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `dashscope_api_key` | str | `""` | Shared key for LLM and embeddings; env `DASHSCOPE_API_KEY`. Recommended alongside `ULTRON_*` in `~/.ultron/.env`. On `Ultron(...)` init, a non-empty value is synced to `os.environ` |

### Embedding model

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `embedding_model` | str | `text-embedding-v4` | DashScope TextEmbedding model name |
| `embedding_dimension` | int | `1024` | Vector dimension (refined by the API after the first call) |
| `embedding_backend` | str | `dashscope` | Embedding backend: `dashscope` or `local`; a single service data directory may use only one backend/model combination |

### LLM configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `llm_provider` | str | `dashscope` | OpenAI-compatible backend id (`dashscope`, `openai`, etc.) |
| `llm_model` | str | `qwen3.6-flash` | Main-path LLM (smart ingestion, summaries, merges, etc.); prefers env `ULTRON_MODEL` |
| `memory_category_llm_model` | str | `qwen3.6-flash` | LLM for memory **type** classification (error/security/…) |
| `skill_category_llm_model` | str | `qwen3.6-flash` | LLM for skill catalog taxonomy |
| `llm_base_url` | str | `https://dashscope.aliyuncs.com/compatible-mode/v1` | OpenAI-compatible API root URL; prefers env `ULTRON_BASE_URL` |
| `llm_api_key` | str | `""` | LLM API key; resolves in order: `ULTRON_API_KEY`, `ULTRON_LLM_API_KEY`, `OPENAI_API_KEY`, `DASHSCOPE_API_KEY` |
| `llm_max_input_tokens` | int | `200000` | User-facing body token budget cap |
| `llm_prompt_reserve_tokens` | int | `8192` | Reserved tokens for system prompt, etc.; **not** counted in the user body budget above |
| `llm_token_count_encoding` | str | `cl100k_base` | tiktoken encoding name (truncation and counting) |
| `llm_request_timeout_seconds` | int | `600` | DashScope HTTP read timeout (seconds); effective value **not below 60** |
| `llm_max_retries` | int | `2` | Retries after the first failed request (total attempts = this value + 1) |
| `llm_retry_base_delay_seconds` | float | `1.0` | Base delay (seconds) for retry backoff |

### Trajectory metrics

Ultron injects its separately configured trajectory metric model into `ms_agent.trajectory`. This uses the `quality_llm_*` configuration slot, but the output is metric JSON and a weighted score.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `quality_llm_provider` | str | `dashscope` | Metric model provider; env `ULTRON_QUALITY_LLM_PROVIDER` |
| `quality_llm_model` | str | `qwen3.6-plus` | Metric model name; env `ULTRON_QUALITY_LLM_MODEL` |
| `quality_llm_base_url` | str | Same default as main LLM | Metric model OpenAI-compatible base URL; env `ULTRON_QUALITY_LLM_BASE_URL` |
| `quality_llm_api_key` | str | `""` (falls back to main LLM) | Metric model API key; env `ULTRON_QUALITY_LLM_API_KEY` |
| `trajectory_memory_score_threshold` | float | `0.7` | Same 0–1 scale as `summary.overall_score` in `quality_metrics` for the memory coarse filter; env `ULTRON_TRAJECTORY_MEMORY_SCORE_THRESHOLD` |
| `trajectory_sft_score_threshold` | float | `0.8` | Same scale as `summary.overall_score` for SFT export/self-training; env `ULTRON_TRAJECTORY_SFT_SCORE_THRESHOLD` |

### Trajectory session → memory extraction

Used by the **`TrajectoryService.extract_memories_from_segments`** facade; implementation is **`TrajectoryMemoryExtractor`**. Reads segment messages from the session **`.jsonl`** on disk when segments pass `trajectory_memory_score_threshold` and `is_memory_eligible`, then token-window extraction into the Memory Hub. See [Trajectory Hub](TrajectoryHub.md).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `conversation_extract_window_tokens` | int | `65536` (effective minimum `256`) | Split the stitched dialogue into token windows and call the main LLM’s `extract_memories_from_text` once per window; env `ULTRON_CONVERSATION_EXTRACT_WINDOW_TOKENS` |
| `session_extract_overlap_lines` | int | `5` | Before the “new tail”, take **K more lines** backward from the `.jsonl` as context; env `ULTRON_SESSION_EXTRACT_OVERLAP_LINES`, minimum `0` |

### Memory tiers

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `hot_percentile` | int | `10` | HOT tier percentile (top N%), reassigned periodically by `run_tier_rebalance` |
| `warm_percentile` | int | `40` | WARM tier percentile (next M%) |
| `cold_ttl_days` | int | `30` | Archive COLD memories as archived after N days (`0` = no archival) |

### Search and intent

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable_intent_analysis` | bool | `True` | Whether to run query intent analysis before memory semantic search |
| `memory_search_default_limit` | int | `10` | Max rows returned when `limit` is **not** passed (`MemoryService.search_memories`, HTTP `POST /memory/search`, etc.) |
| `skill_search_default_limit` | int | `5` | Max rows returned when `limit` is **not** passed (`search_skills`, HTTP `POST /skills/search`, etc.) |

### Dedup and merge

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `dedup_similarity_threshold` | float | `0.85` | Cosine threshold for near-duplicate detection (hard dedup) |
| `dedup_soft_threshold` | float | `0.75` | Soft threshold; hits are double-checked by LLM for duplicates |
| `memory_merge_max_field_tokens` | int | `8192` | Max tokens per field after merge (`0` = no truncation) |

### L0 / L1 / full tiering

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `l0_max_tokens` | int | `64` | L0 summary max token count |
| `l1_max_tokens` | int | `256` | L1 overview max token count |

### Time decay

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `decay_interval_hours` | float | `6.0` | Interval (hours) for the server background memory decay job |
| `decay_alpha` | float | `0.05` | Time freshness coefficient: `hotness = exp(-alpha * days_since_last_hit)` |
| `time_decay_weight` | float | `0.1` | Weight combined with `hotness` in retrieval ranking |

### Async embedding

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `async_embedding` | bool | `False` | Whether to enable the async embedding queue |
| `embedding_queue_size` | int | `100` | Max queue capacity |
| `embedding_queue_workers` | int | `2` | Number of background workers |

### Raw upload archive (fixed behavior, no switch)

With a persistent database, raw content is written to `raw_user_uploads` (no opt-out): one `ingest_file` row per `.jsonl` ingested via `ingest(paths)`; one `ingest_text` row per standalone **`ingest_text`**; one `skill_upload_file` row per file under **`upload_skill`**. **`upload_memory` is not archived**. Single payload ≤10MB; full HTTP JSON bodies are not stored.

### Consolidation (chain-merge)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `consolidate_enabled` | bool | `False` | Whether to run consolidation automatically during tier rebalance |
| `consolidate_max_merges` | int | `50` | Max merge operations per consolidation run |

### Skill evolution

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `evolution_enabled` | bool | `True` | Whether to enable the skill evolution pipeline (cluster → crystallize → recrystallize) |
| `cluster_similarity_threshold` | float | `0.75` | Cosine similarity threshold for assigning a memory to a cluster |
| `crystallization_threshold` | int | `5` | Crystallize when the cluster reaches this many memories |
| `recrystallization_delta` | int | `3` | Re-crystallize when this many new memories land on a crystallized cluster |
| `evolution_batch_limit` | int | `10` | Max clusters to evolve per batch |

### Authentication

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `jwt_secret` | str | auto-generated | JWT signing secret; may be passed in the constructor; otherwise reads `ULTRON_JWT_SECRET`, then `data_dir/.jwt_secret`, else generates and persists (see `resolve_jwt_secret()`) |
| `jwt_expire_hours` | int | `24` | JWT token lifetime (hours) |

## Environment variables

HTTP logging: see [Installation](../GetStarted/Installation.md) (`ULTRON_LOG_LEVEL`, `ULTRON_RESET_TOKEN`, etc. are not `UltronConfig` fields).

| Environment variable | Mapped field |
|---------------------|--------------|
| `DASHSCOPE_API_KEY` | `dashscope_api_key` |
| `ULTRON_DATA_DIR` | `data_dir` |
| `ULTRON_DB_NAME` | `db_name` |
| `ULTRON_EMBEDDING_BACKEND` | `embedding_backend` |
| `ULTRON_EMBEDDING_MODEL` | `embedding_model` |
| `ULTRON_EMBEDDING_DIMENSION` | `embedding_dimension` |
| `ULTRON_CONVERSATION_EXTRACT_WINDOW_TOKENS` | `conversation_extract_window_tokens` |
| `ULTRON_TRAJECTORY_MEMORY_SCORE_THRESHOLD` | `trajectory_memory_score_threshold` |
| `ULTRON_TRAJECTORY_SFT_SCORE_THRESHOLD` | `trajectory_sft_score_threshold` |
| `ULTRON_SESSION_EXTRACT_OVERLAP_LINES` | `session_extract_overlap_lines` |
| `ULTRON_QUALITY_LLM_PROVIDER` | `quality_llm_provider` |
| `ULTRON_QUALITY_LLM_MODEL` | `quality_llm_model` |
| `ULTRON_QUALITY_LLM_BASE_URL` | `quality_llm_base_url` |
| `ULTRON_QUALITY_LLM_API_KEY` | `quality_llm_api_key` |
| `ULTRON_HOT_PERCENTILE` | `hot_percentile` |
| `ULTRON_WARM_PERCENTILE` | `warm_percentile` |
| `ULTRON_COLD_TTL_DAYS` | `cold_ttl_days` |
| `ULTRON_DEDUP_SIMILARITY_THRESHOLD` | `dedup_similarity_threshold` |
| `ULTRON_MEMORY_MERGE_MAX_FIELD_TOKENS` | `memory_merge_max_field_tokens` |
| `ULTRON_L0_MAX_TOKENS` | `l0_max_tokens` |
| `ULTRON_L1_MAX_TOKENS` | `l1_max_tokens` |
| `ULTRON_ENABLE_INTENT_ANALYSIS` | `enable_intent_analysis` |
| `ULTRON_MEMORY_SEARCH_LIMIT` | `memory_search_default_limit` |
| `ULTRON_SKILL_SEARCH_LIMIT` | `skill_search_default_limit` |
| `ULTRON_ASYNC_EMBEDDING` | `async_embedding` |
| `ULTRON_EMBEDDING_QUEUE_SIZE` | `embedding_queue_size` |
| `ULTRON_EMBEDDING_QUEUE_WORKERS` | `embedding_queue_workers` |
| `ULTRON_DECAY_INTERVAL_HOURS` | `decay_interval_hours` |
| `ULTRON_DECAY_ALPHA` | `decay_alpha` |
| `ULTRON_TIME_DECAY_WEIGHT` | `time_decay_weight` |
| `ULTRON_LLM_PROVIDER` | `llm_provider` |
| `ULTRON_MODEL` | `llm_model` |
| `ULTRON_LLM_MODEL` | `llm_model` (compat fallback) |
| `ULTRON_MEMORY_CATEGORY_MODEL` | `memory_category_llm_model` |
| `ULTRON_SKILL_CATEGORY_MODEL` | `skill_category_llm_model` |
| `ULTRON_BASE_URL` | `llm_base_url` |
| `ULTRON_LLM_BASE_URL` | `llm_base_url` (compat fallback) |
| `ULTRON_LLM_API_URL` | `llm_base_url` (compat fallback) |
| `ULTRON_API_KEY` | `llm_api_key` |
| `ULTRON_LLM_API_KEY` | `llm_api_key` (compat fallback) |
| `ULTRON_LLM_MAX_INPUT_TOKENS` | `llm_max_input_tokens` |
| `ULTRON_LLM_PROMPT_RESERVE_TOKENS` | `llm_prompt_reserve_tokens` |
| `ULTRON_LLM_TOKEN_COUNT_ENCODING` | `llm_token_count_encoding` |
| `ULTRON_LLM_REQUEST_TIMEOUT` | `llm_request_timeout_seconds` |
| `ULTRON_LLM_MAX_RETRIES` | `llm_max_retries` |
| `ULTRON_LLM_RETRY_BASE_DELAY` | `llm_retry_base_delay_seconds` |
| `ULTRON_DEDUP_SOFT_THRESHOLD` | `dedup_soft_threshold` |
| `ULTRON_CONSOLIDATE_ENABLED` | `consolidate_enabled` |
| `ULTRON_CONSOLIDATE_MAX_MERGES` | `consolidate_max_merges` |
| `ULTRON_EVOLUTION_ENABLED` | `evolution_enabled` |
| `ULTRON_CLUSTER_SIMILARITY_THRESHOLD` | `cluster_similarity_threshold` |
| `ULTRON_CRYSTALLIZATION_THRESHOLD` | `crystallization_threshold` |
| `ULTRON_RECRYSTALLIZATION_DELTA` | `recrystallization_delta` |
| `ULTRON_EVOLUTION_BATCH_LIMIT` | `evolution_batch_limit` |
| `ULTRON_JWT_SECRET` | `jwt_secret` |
| `ULTRON_JWT_EXPIRE_HOURS` | `jwt_expire_hours` |

## Directory properties

`UltronConfig` exposes convenient directory path properties:

```python
config = UltronConfig()

config.db_path           # ~/.ultron/ultron.db
config.skills_dir        # ~/.ultron/skills
config.archive_dir       # ~/.ultron/archive
config.models_dir        # ~/.ultron/models
```
