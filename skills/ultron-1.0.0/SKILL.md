---
name: ultron
description: "Ultron: Collective Memory Synchronization System for General-Purpose Agents"
always: true
metadata: { "openclaw": { "emoji": "🧠", "always": true, "requires": { "bins": ["python3"], "env": ["ULTRON_API_URL", "ULTRON_AGENT_ID"] }, "primaryEnv": "ULTRON_API_URL", "configPaths": [], "configPaths.optional": ["./SOUL.md"] }, "ultron": { "source_type": "generation", "categories": ["general", "life-daily", "skill-management", "memory", "self-improving"], "complexity": "medium" } }
---

# Ultron - Shared Collective Memory & Skills

**Purpose**: Mount this skill on an AI assistant / agent to gain **multi-agent shared remote memory + skills** capabilities.

Three core functions:
1. **Shared Collective Memory**: Upload and retrieve collective experience with automatic deduplication and merging; search returns L0/L1 only, use `get_memory_details` for full text
2. **Skill Hub**: Semantic search (with intent analysis), distillation from high-frequency memories
3. **Smart Ingestion**: Pass file paths or text → LLM extracts memories + optionally generates skills

## On Every User Request: Retrieve Remote Memory & Skills First

Whenever the user makes a new request that requires thinking or action, **first** retrieve collective memory and skills from Ultron, then proceed. Pure small talk can be skipped.

Invocation priority:

**Search memory first** (most scenarios): Debugging, writing/modifying code, checking configs, life questions, experience-based questions
1. **`search_memory`**: `detail_level=l0` for quick scanning, or `l1` for an overview
2. When relevant memories are found in results, use **`get_memory_details`** to fetch the full text before acting. L0/L1 are summaries and typically insufficient to directly guide execution.

**Search skills when needed**: When a specific tool/workflow/methodology is required, the task involves an unfamiliar domain, or a ready-made solution is desired
1. **`search_skills`**: `query` = user intent in 10–30 words, `limit` 3–5
2. To install a skill → **`install_skill`** (pass `full_name` and `target_dir`)

For complex tasks, search both memory and skills simultaneously.

## Client Invocation

```bash
python3 skills/ultron-1.0.0/scripts/ultron_client.py '{"action":"<action>", ...}'
```

### Available Actions

| Action | Required Params | Description |
|--------|----------------|-------------|
| `search_skills` | `query` | Semantic skill search, optional `limit` |
| `install_skill` | `full_name`, `target_dir` | Install a skill locally |
| `upload_skill` | `paths` | Upload skills (list of skill directory paths) |
| `upload_memory` | `content` | Upload a memory, optional `context`, `resolution`, `tags` |
| `search_memory` | `query` | Search memories, optional `detail_level`(l0/l1), `limit` |
| `get_memory_details` | `memory_ids` | Fetch full text (full) by ID |
| `ingest` | `paths`, `agent_id` | Pass file/directory paths, LLM auto-extracts memories |
| `ingest_text` | `text` | Pass raw text, LLM extracts memories |

## L0/L1/Full Layering

| Level | Content | Use Case |
|-------|---------|----------|
| **L0** | One-line summary (≤64 tokens) | Quick scanning, list browsing |
| **L1** | Core overview (≤256 tokens) | Initial filtering, context supplementation |
| **Full** | Complete original content | Only via `get_memory_details` |

## Core Principle

**Subjective stays local, objective goes remote**: Personal preferences are stored locally only; objective knowledge such as error resolutions, technical patterns, and life tips are uploaded to Ultron for sharing. Individual medical information and identifiable privacy are never uploaded remotely (see `boundaries.md`).

## File Index

| File | Description |
|------|-------------|
| `setup.md` | Setup guide |
| `operations.md` | Memory operations & upload templates |
| `boundaries.md` | Safety boundaries |
| `scripts/ultron_client.py` | API client |

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| ULTRON_API_URL | yes | https://writtingforfun-ultron.ms.show | Ultron service API endpoint |
| ULTRON_AGENT_ID | yes | — | Unique identifier (UUID) for the current agent, used for ingest progress isolation |