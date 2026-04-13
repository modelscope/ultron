---
slug: Config
title: Configuration
description: UltronConfig and environment variables
---

# Configuration

Ultron uses the `UltronConfig` dataclass. **`ULTRON_*` environment variables** and **`DASHSCOPE_API_KEY`** supply defaults; explicit arguments to `UltronConfig(...)` **override** the environment. `DASHSCOPE_API_KEY` maps to `dashscope_api_key`; when constructing `Ultron`, a non-empty value is written to `os.environ["DASHSCOPE_API_KEY"]` for existing DashScope clients.

On first import of `ultron.config` (or `import ultron`), `load_ultron_dotenv()` loads `~/.ultron/.env` into `os.environ` (`override=False`).

- The repo provides `.env.example`; copy `DASHSCOPE_API_KEY` and `ULTRON_*` into `~/.ultron/.env` (create the directory if needed).
- Without **`python-dotenv`**, `load_ultron_dotenv()` is a no-op; use exported variables or your process manager.

## Configure in code

```python
from ultron import Ultron, UltronConfig

config = UltronConfig(
    data_dir="~/.ultron",
    embedding_model="text-embedding-v4",
    llm_model="qwen3.5-flash",
    dedup_similarity_threshold=0.85,
)

ultron = Ultron(config=config)
```

## Settings reference

### Data storage

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `data_dir` | str | `~/.ultron` | Root data directory |
| `db_name` | str | `ultron.db` | SQLite filename |

### DashScope credentials

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `dashscope_api_key` | str | `""` | Shared key for LLM and embeddings; env `DASHSCOPE_API_KEY`. Non-empty value is synced to `os.environ` on `Ultron(...)` init |

### Embedding model

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `embedding_model` | str | `text-embedding-v4` | DashScope TextEmbedding model |
| `embedding_dimension` | int | `1024` | Vector size (API may refine after first call) |

### LLM

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `llm_model` | str | `qwen3.5-flash` | Main LLM (ingestion, summaries, merges) |
| `memory_category_llm_model` | str | `qwen3.5-flash` | LLM for memory **type** (error/security/…) |
| `skill_category_llm_model` | str | `qwen3.5-flash` | LLM for skill taxonomy |
| `llm_api_url` | str | `https://dashscope.aliyuncs.com/api/v1` | DashScope-compatible API root |
| `llm_max_input_tokens` | int | `200000` | User text token budget cap |
| `llm_prompt_reserve_tokens` | int | `8192` | Reserved tokens for system prompt (**not** counted in user budget) |
| `llm_token_count_encoding` | str | `cl100k_base` | tiktoken encoding for truncation |
| `llm_request_timeout_seconds` | int | `600` | HTTP read timeout; effective value **not below 60** |
| `llm_max_retries` | int | `2` | Retries after failure (total attempts = value + 1) |
| `llm_retry_base_delay_seconds` | float | `1.0` | Backoff base (seconds) |

### Memory tiers

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `hot_percentile` | int | `10` | HOT tier top N% for `run_tier_rebalance` |
| `warm_percentile` | int | `40` | WARM tier next M% |
| `cold_ttl_days` | int | `30` | Archive COLD after N days (0 = no archival) |

### Search and intent

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable_intent_analysis` | bool | `True` | Query intent analysis before memory semantic search |
| `memory_search_default_limit` | int | `10` | Default `limit` when omitted (`MemoryService.search_memories`, `POST /memory/search`, …) |
| `skill_search_default_limit` | int | `5` | Default `limit` when omitted (`search_skills`, `POST /skills/search`, …) |
| `skill_auto_detect_batch_limit` | int | `5` | HOT candidate cap for `auto_detect_and_generate` / `auto_generate_skills` when `limit` omitted |

### Dedup and merge

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `dedup_similarity_threshold` | float | `0.85` | Cosine threshold for near-duplicate detection |
| `memory_merge_max_field_tokens` | int | `8192` | Max tokens per merged field (0 = no truncation) |

### L0 / L1 / full

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `l0_max_tokens` | int | `64` | L0 summary cap |
| `l1_max_tokens` | int | `256` | L1 overview cap |

### Session extraction

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `session_extract_overlap_lines` | int | `5` | Leading context lines for incremental extract |
| `conversation_extract_window_tokens` | int | `65536` | Per-window token cap (parsed **not below 256**) |

### Time decay

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `decay_interval_hours` | float | `6.0` | Background decay job interval |
| `decay_alpha` | float | `0.05` | Freshness: `hotness = exp(-alpha * days_since_last_hit)` |
| `time_decay_weight` | float | `0.1` | Blend weight with `hotness` in ranking |

### Async embedding

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `async_embedding` | bool | `False` | Enable async embedding queue |
| `embedding_queue_size` | int | `100` | Queue capacity |
| `embedding_queue_workers` | int | `2` | Worker count |

### Archiving (ingestion and skill packs)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `archive_raw_uploads` | bool | `True` | When true: `ingest(paths)` writes each file’s bytes to `raw_user_uploads` (`source=ingest_file`); standalone `ingest_text` writes UTF-8 text (`source=ingest_text`); `upload_skill` writes each file under the pack (`skill_upload_file`). **`upload_memory` is not archived**. Single payload ≤10MB. Full HTTP JSON bodies are not stored. |

## Environment variable mapping

HTTP logging and `/reset` auth are covered in [Installation](../GetStarted/Installation.md) (`ULTRON_LOG_LEVEL`, `ULTRON_RESET_TOKEN` are not part of `UltronConfig`).

| Environment variable | Config field |
|---------------------|--------------|
| `DASHSCOPE_API_KEY` | `dashscope_api_key` |
| `ULTRON_DATA_DIR` | `data_dir` |
| `ULTRON_DB_NAME` | `db_name` |
| `ULTRON_EMBEDDING_MODEL` | `embedding_model` |
| `ULTRON_EMBEDDING_DIMENSION` | `embedding_dimension` |
| `ULTRON_HOT_PERCENTILE` | `hot_percentile` |
| `ULTRON_WARM_PERCENTILE` | `warm_percentile` |
| `ULTRON_COLD_TTL_DAYS` | `cold_ttl_days` |
| `ULTRON_DEDUP_SIMILARITY_THRESHOLD` | `dedup_similarity_threshold` |
| `ULTRON_SESSION_EXTRACT_OVERLAP_LINES` | `session_extract_overlap_lines` |
| `ULTRON_CONVERSATION_EXTRACT_WINDOW_TOKENS` | `conversation_extract_window_tokens` |
| `ULTRON_MEMORY_MERGE_MAX_FIELD_TOKENS` | `memory_merge_max_field_tokens` |
| `ULTRON_L0_MAX_TOKENS` | `l0_max_tokens` |
| `ULTRON_L1_MAX_TOKENS` | `l1_max_tokens` |
| `ULTRON_ENABLE_INTENT_ANALYSIS` | `enable_intent_analysis` |
| `ULTRON_MEMORY_SEARCH_LIMIT` | `memory_search_default_limit` |
| `ULTRON_SKILL_SEARCH_LIMIT` | `skill_search_default_limit` |
| `ULTRON_SKILL_AUTO_DETECT_LIMIT` | `skill_auto_detect_batch_limit` |
| `ULTRON_ASYNC_EMBEDDING` | `async_embedding` |
| `ULTRON_EMBEDDING_QUEUE_SIZE` | `embedding_queue_size` |
| `ULTRON_EMBEDDING_QUEUE_WORKERS` | `embedding_queue_workers` |
| `ULTRON_DECAY_INTERVAL_HOURS` | `decay_interval_hours` |
| `ULTRON_DECAY_ALPHA` | `decay_alpha` |
| `ULTRON_TIME_DECAY_WEIGHT` | `time_decay_weight` |
| `ULTRON_LLM_MODEL` | `llm_model` |
| `ULTRON_MEMORY_CATEGORY_MODEL` | `memory_category_llm_model` |
| `ULTRON_SKILL_CATEGORY_MODEL` | `skill_category_llm_model` |
| `ULTRON_LLM_API_URL` | `llm_api_url` |
| `ULTRON_LLM_MAX_INPUT_TOKENS` | `llm_max_input_tokens` |
| `ULTRON_LLM_PROMPT_RESERVE_TOKENS` | `llm_prompt_reserve_tokens` |
| `ULTRON_LLM_TOKEN_COUNT_ENCODING` | `llm_token_count_encoding` |
| `ULTRON_LLM_REQUEST_TIMEOUT` | `llm_request_timeout_seconds` |
| `ULTRON_LLM_MAX_RETRIES` | `llm_max_retries` |
| `ULTRON_LLM_RETRY_BASE_DELAY` | `llm_retry_base_delay_seconds` |
| `ULTRON_ARCHIVE_RAW_UPLOADS` | `archive_raw_uploads` |

## Directory helpers

`UltronConfig` exposes path properties:

```python
config = UltronConfig()

config.db_path           # ~/.ultron/ultron.db
config.skills_dir        # ~/.ultron/skills
config.archive_dir       # ~/.ultron/archive
config.models_dir        # ~/.ultron/models
```
