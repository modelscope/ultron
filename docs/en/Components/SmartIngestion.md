---
slug: SmartIngestion
title: Smart ingestion
description: Unified file and text ingestion with LLM extraction
---

# Smart ingestion

Smart Ingestion is Ultron’s unified extraction pipeline. Pass file or directory paths or raw text; Ultron routes by type: `.jsonl` sessions go through ConversationExtractor (incremental), everything else through LLM text extraction.

## Capabilities

| Capability | Description |
|------------|-------------|
| **Unified ingest** | Single `ingest(paths)` entry; extension-based routing |
| **Text ingest** | Raw string path |
| **Session extract** | `.jsonl` uses incremental session logic |
| **Directory walk** | Recurses into directories (skips hidden segments and symlinks) |
| **Type detection** | Memory type inferred automatically |
| **Dedup** | Merges with existing memories |
| **Raw archive** | When `archive_raw_uploads`: one `ingest_file` row per file from `ingest(paths)`; standalone `ingest_text` → `ingest_text`; file-sourced extraction archives file bytes only, not duplicate decoded text |

## Examples

### Unified ingest

```python
from ultron import Ultron

ultron = Ultron()

result = ultron.ingest(
    paths=["/path/to/debug_log.txt", "/path/to/sessions/"],
)

print(result["total_files"], result["total_memories"])
```

### Text ingest

```python
result = ultron.ingest_text(
    text="""
    Debug notes:
    1. pip install failed in Docker
    2. Error: Could not find a version that satisfies...
    3. Cause: no network in container
    4. Fix: configure proxy or use --network host
    """,
)

for mem in result.get("memories", []):
    print(mem["memory_type"], mem["content"][:50])
```

## Flow

### Router

```
Path list
  -> expand directories
  -> archive raw bytes to raw_user_uploads (skip >10MB; archive errors do not block)
  -> per file:
       .jsonl -> ConversationExtractor (incremental)
       else   -> LLM text extraction
  -> upload to MemoryService (dedup, tier promotion)
  -> aggregate result
```

### Session `.jsonl`

```
session file -> read new lines (incremental)
  -> sliding windows (conversation_extract_window_tokens)
  -> LLM extracts reusable lessons
  -> MemoryService upload
```

## Incremental sessions

1. Server tracks last processed line per file path
2. Each run processes only new lines
3. `session_extract_overlap_lines` prepends context before new lines

```python
ultron.ingest(paths=["/path/to/session.jsonl"])
# later, after append:
ultron.ingest(paths=["/path/to/session.jsonl"])
```

## LLM extraction

Default model `qwen3.5-flash`. The model extracts reusable experience:

- Errors and fixes
- Security lessons
- General patterns
- Shareable life tips (no private PII)

### Output shape

```json
{
  "memories": [
    {
      "content": "problem",
      "context": "scenario",
      "resolution": "fix",
      "confidence": 0.85,
      "tags": ["python", "docker"]
    }
  ]
}
```

## Token budgets

| Setting | Role |
|---------|------|
| `llm_max_input_tokens` | Max input tokens |
| `llm_prompt_reserve_tokens` | Budget reserved for the model reply |
| `conversation_extract_window_tokens` | Session window size |

Long inputs are truncated or split automatically.

## HTTP

### Unified ingest

```
POST /ingest
{"paths": ["/path/to/file.txt", "/path/to/sessions/"]}
```

### Text

```
POST /ingest/text
{"text": "..."}
```

## Requirements

1. `DASHSCOPE_API_KEY`
2. LLM reachable (default `qwen3.5-flash`)

If the LLM is unavailable, behavior falls back to rule-based type hints where applicable.

## Practices

1. Batch mixed paths in one `ingest(paths=[...])` call
2. Point Heartbeat at a sessions directory; `.jsonl` stays incremental
3. Tune `min_confidence` if you need stricter extraction quality
