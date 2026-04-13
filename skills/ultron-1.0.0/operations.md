# Memory Operations

## Retrieval

### L0/L1 Search & Full Details

```bash
# L0 quick scan — returns id + one-line summary + type only
search_memory(query="...", detail_level="l0", limit=10)

# L1 overview — returns L0 + overview + tags
search_memory(query="...", detail_level="l1", limit=5)

# Full text — only via get_memory_details
get_memory_details(memory_ids=["id-1", "id-2"])
```

## Upload

### upload_memory (Manual Upload)

```json
{
  "action": "upload_memory",
  "content": "Full description of the problem or experience",
  "context": "Environment / scenario where it occurred",
  "resolution": "Solution or conclusion",
  "tags": ["tag1", "tag2"]
}
```

Examples:

```json
{"content": "ModuleNotFoundError: No module named 'pandas'", "context": "Running a Python script inside a Docker container", "resolution": "pip install pandas", "tags": ["python", "docker"]}
{"content": "Must activate venv before pip install", "context": "Python development environment", "resolution": "source venv/bin/activate && pip install xxx", "tags": ["python", "venv"]}
```

### ingest / ingest_text (Smart Ingestion, Recommended)

For complex content, let the LLM automatically extract structured memories:

```json
{"action": "ingest_text", "text": "Debugging process: first check the Python version..."}
{"action": "ingest", "paths": ["/path/to/debug.jsonl"], "agent_id": "<ULTRON_AGENT_ID>"}
```

## Automatic Operations

- **On receiving a correction**: Objective experience → upload via `upload_memory` or `ingest_text`; subjective preference → local only
- **On encountering valuable experience**: Pass files to `ingest` or text to `ingest_text`, Ultron auto-extracts

See `boundaries.md` for rules on determining subjective vs. objective before uploading.