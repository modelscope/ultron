---
slug: Installation
title: Server deployment
description: How to self-host the Ultron server
---

# Server deployment

This guide explains how to run your own Ultron service. If you only need an assistant to connect to an existing Ultron instance (self-hosted or public), see [Agent setup](AgentSetup.md).

## Install from source

```shell
git clone https://github.com/modelscope/ultron.git
cd ultron
pip install -e .
```

## Dependencies

Core dependencies (see `requirements.txt`):

| Package | Purpose |
|---------|---------|
| `fastapi` | HTTP framework |
| `uvicorn` | ASGI server |
| `pydantic` | Validation |
| `tiktoken` | Token counting |
| `dashscope` | LLM and text embeddings |

## Runtime

| Requirement | Notes |
|-------------|-------|
| Python | >= 3.8 |
| OS | Linux / macOS / Windows |

Ultron primarily calls LLM APIs, so a CPU-only machine is enough.

## Environment variables

Smart ingestion and LLM-based classification need a DashScope API key (`DASHSCOPE_API_KEY`, mapped to `UltronConfig.dashscope_api_key`). **Recommended**: add one line `DASHSCOPE_API_KEY=...` to `~/.ultron/.env` alongside any `ULTRON_*` keys; when you construct `Ultron`, the value is synced into the process environment for the DashScope SDK.

You can also export in the shell for one-off debugging:

```shell
export DASHSCOPE_API_KEY="your-api-key"
```

Using `~/.ultron/.env` requires `python-dotenv`; see the repo root `.env.example`. Importing `ultron` only auto-loads `~/.ultron/.env` (see [Configuration](../Components/Config.md)). In systemd, Docker, etc., inject the same variable names.

Other optional variables (full `ULTRON_*` list in [Configuration](../Components/Config.md)); constructor arguments to `UltronConfig(...)` override the environment.

### DashScope / models

| Variable | Description | Default |
|----------|-------------|---------|
| `ULTRON_EMBEDDING_MODEL` | TextEmbedding model name | `text-embedding-v4` |
| `ULTRON_EMBEDDING_DIMENSION` | Vector dimension | `1024` |
| `ULTRON_LLM_MODEL` | LLM for smart ingestion and extraction | `qwen3.5-flash` |
| `ULTRON_MEMORY_CATEGORY_MODEL` | LLM for memory type classification | `qwen3.5-flash` |
| `ULTRON_SKILL_CATEGORY_MODEL` | LLM for skill taxonomy | `qwen3.5-flash` |
| `ULTRON_LLM_API_URL` | DashScope-compatible API base | `https://dashscope.aliyuncs.com/api/v1` |

### LLM request control

| Variable | Description | Default |
|----------|-------------|---------|
| `ULTRON_LLM_MAX_INPUT_TOKENS` | Max user text tokens | `200000` |
| `ULTRON_LLM_PROMPT_RESERVE_TOKENS` | Reserved tokens for system prompt | `8192` |
| `ULTRON_LLM_TOKEN_COUNT_ENCODING` | tiktoken encoding name | `cl100k_base` |
| `ULTRON_LLM_REQUEST_TIMEOUT` | HTTP read timeout (seconds) | `600` |
| `ULTRON_LLM_MAX_RETRIES` | Retries after failure | `2` |
| `ULTRON_LLM_RETRY_BASE_DELAY` | Base backoff (seconds) | `1.0` |

### Memory extraction

| Variable | Description | Default |
|----------|-------------|---------|
| `ULTRON_SESSION_EXTRACT_OVERLAP_LINES` | Overlap lines for incremental extract | `5` |
| `ULTRON_CONVERSATION_EXTRACT_WINDOW_TOKENS` | Max tokens per LLM window | `65536` |
| `ULTRON_MEMORY_MERGE_MAX_FIELD_TOKENS` | Max tokens per field when merging | `8192` |

### Search responses

| Variable | Description | Default |
|----------|-------------|---------|
| `ULTRON_L0_MAX_TOKENS` | Max tokens for L0 summary in results | `64` |
| `ULTRON_L1_MAX_TOKENS` | Max tokens for L1 snippet in results | `256` |

### Tiers, dedup, decay (subset)

| Variable | Description | Default |
|----------|-------------|---------|
| `ULTRON_DATA_DIR` | Data root (`~` expanded) | `~/.ultron` |
| `ULTRON_DB_NAME` | SQLite filename | `ultron.db` |
| `ULTRON_HOT_MAX_ENTRIES` | HOT tier max entries | `500` |
| `ULTRON_WARM_MAX_ENTRIES` | WARM tier max entries | `1000` |
| `ULTRON_HOT_PERCENTILE` | HOT percentile | `10` |
| `ULTRON_DEDUP_SIMILARITY_THRESHOLD` | Cosine threshold for near-duplicate | `0.85` |
| `ULTRON_ENABLE_INTENT_ANALYSIS` | Intent analysis before search (`0` off) | `1` |
| `ULTRON_MEMORY_SEARCH_LIMIT` | Default memory search limit | `10` |
| `ULTRON_SKILL_SEARCH_LIMIT` | Default skill search limit | `5` |
| `ULTRON_SKILL_AUTO_DETECT_LIMIT` | HOT batch limit for auto skill generation | `5` |
| `ULTRON_DECAY_INTERVAL_HOURS` | Decay job interval (hours) | `6.0` |
| `ULTRON_DECAY_ALPHA` | Freshness coefficient | `0.05` |
| `ULTRON_COLD_TTL_DAYS` | COLD retention days (`0` = never delete) | `30` |

### Service and storage

| Variable | Description | Default |
|----------|-------------|---------|
| `ULTRON_LOG_LEVEL` | Log level | `INFO` |
| `ULTRON_RESET_TOKEN` | Auth token for `/reset` (unset disables) | none |
| `ULTRON_ARCHIVE_RAW_UPLOADS` | Archive ingest files, ingest_text payloads, skill uploads (not `upload_memory`) | `1` |

More fields (async embedding queue, hot summary caps, etc.) are documented in [Configuration](../Components/Config.md).

## Run the service

### HTTP server

```shell
uvicorn ultron.server:app --host 0.0.0.0 --port 9999
# Default http://0.0.0.0:9999
```

### As a library

```python
from ultron import Ultron

ultron = Ultron()
# ...
```

## Data directory

Default `UltronConfig.data_dir` is `~/.ultron/`. The library uses:

| Path | Purpose |
|------|---------|
| `ultron.db` | SQLite database |
| `skills/` | Skill content |
| `archive/` | Archived skills |
| `models/` | Local model cache |

When you start `ultron.server:app` with uvicorn, structured JSON logs go to `~/.ultron/logs/` (`ultron.log` and rotated backups).

Override paths with `ULTRON_DATA_DIR`, `Ultron(config=UltronConfig(data_dir=...))`, or `Ultron(data_dir=...)`.

## Next steps

After the server is up, follow [Agent setup](AgentSetup.md) to connect your assistant to Ultron.
