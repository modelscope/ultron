---
slug: Introduction
title: Introduction
description: Ultron self-evolving collective intelligence for AI agents (Memory Hub, Skill Hub, Harness Hub)
---

# Quick start

Ultron is a **self-evolving collective intelligence system** for general AI agents. It is built around three hubs: **Memory Hub**, **Skill Hub**, and **Harness Hub**. It turns fragmented, session-local experience into **group knowledge that is easy to retrieve and reuse**: one resolved pitfall can protect everyone; one effective fix can become a reusable playbook that **keeps evolving automatically as new knowledge arrives**; a carefully tuned agent profile can be published as a **shared blueprint** that other instances **load in one step**.

## Core capabilities

### 💭 Memory Hub

| Capability | Description |
|------------|-------------|
| **Tiered storage** | HOT / WARM / COLD tiers, periodically reassigned by `hit_count` percentile; semantic retrieval with embedding similarity and tier weighting |
| **L0 / L1 / Full context** | Auto-generated one-line summary (L0) and core overview (L1); search returns L0/L1 to save tokens; full text on demand |
| **Automatic type classification** | LLM assigns types (e.g. error, security, life) on upload, with keyword rules as fallback |
| **Deduplication and merge** | Near-duplicate vectors of the same type merge; embeddings and summaries refresh; batch consolidation supported |
| **Intent-expanded retrieval** | LLM-based multi-angle query expansion to improve recall |
| **Time decay** | `hotness = exp(-α × days)` — long-unused memories are down-ranked over time |
| **Smart ingestion** | Files, plain text, or `.jsonl` session logs; LLM extracts structured memories; incremental progress tracking |
| **Data sanitization** | Presidio-based bilingual PII detection; automatic redaction before persistence |

### ⚡ Skill Hub

| Capability | Description |
|------------|-------------|
| **Skill crystallization** | Reusable skills generated when memories enter HOT; direct skill package upload also supported |
| **Skill self-evolution** | Re-crystallizes when cluster delta is reached; traceable provenance verification plus a structure-score upgrade gate so evolution quality does not regress |
| **Unified search** | Internal crystallized skills and 30K+ ModelScope catalog skills share one search API |
| **Improvement suggestions** | Semantically similar memories surface as candidates to enrich existing skills |

### 🏗️ Harness Hub

| Capability | Description |
|------------|-------------|
| **Config publishing** | Publish full agent config (persona + memory + skills) as a shareable blueprint; short-code import |
| **Bidirectional sync** | Upload/download workspace state to the server; continuity across devices |
| **Role presets** | Combine presets (roles, MBTI, zodiac, etc.) into agent personas and workspace assets |

## Four-layer architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                   Ultron                                     │
│  ┌──────────────┐  ┌────────────────┐  ┌───────────────┐  ┌───────────────┐  │
│  │ Smart Ingest │  │ Remote Memory  │  │ Skill Hub     │  │ Harness Hub   │  │
│  │ ingest_*     │  │ HOT/WARM/COLD  │  │ search_skills │  │ publish       │  │
│  │ LLM extract  │  │ L0/L1/full     │  │ upload_skill  │  │ import        │  │
│  │              │  │ dedup + rebal  │  │ skill evolve  │  │ sync profile  │  │
│  │              │  │ intent + decay │  │ LLM catalog   │  │ mem/skill/soul│  │
│  └──────────────┘  └────────────────┘  └───────────────┘  └───────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
          ▲                   ▲                  ▲                   ▲
       Sentry A            Sentry B           Sentry C           Sentry D
```

| Module | Responsibility | Main code |
|--------|----------------|-----------|
| **Smart Ingestion** | Raw files/text → LLM-extracted memories | `services/smart_ingestion.py`, `core/llm_service.py` |
| **Remote Memory** | Shared experience storage, semantic search, percentile tier rebalance | `services/memory/`, `core/database.py` |
| **Skill Hub** | Structured skills, semantic retrieval | `services/skill/`, `core/storage.py` |
| **Harness Hub** | Publish, import, and sync agent harness config | `services/harness/` |

## Installation

- Connect to a deployed Ultron service: **[Quickstart Guide](https://writtingforfun-ultron.ms.show/quickstart)**
- Manual assistant setup: [Agent setup](AgentSetup.md)
- Self-host Ultron: [Server deployment](Installation.md)

## Usage examples

### Python SDK

```python
from ultron import Ultron

ultron = Ultron()

# Smart ingestion (requires LLM)
result = ultron.ingest_text(
    text="Troubleshooting: pip install failed inside Docker...",
)

# Manual memory upload (type decided by server)
rec = ultron.upload_memory(
    content="ModuleNotFoundError: No module named 'pandas'",
    context="Running script inside Docker",
    resolution="pip install pandas",
    tags=["python", "docker"],
)

# Memory search (all types; detail_level l0 or l1; full text via get_memory_details)
rows = ultron.search_memories("Python import", detail_level="l0", limit=10)

# Skill search
skills = ultron.search_skills("how to fix import errors", limit=5)
```

### Run the HTTP server

```shell
uvicorn ultron.server:app --host 0.0.0.0 --port 9999
# Default http://0.0.0.0:9999
```

## Data sources and statistics

### Memories (from [ZClawBench](https://huggingface.co/datasets/zai-org/ZClawBench))

Structured memories refined from real agent trajectories; currently **1,746** records:

| Type | Count | Description |
|------|-------|-------------|
| `pattern` | 1,254 | Recurring patterns and best practices |
| `error` | 196 | Debugging experience and fixes |
| `security` | 128 | Security-related lessons |
| `life` | 122 | Shareable everyday-life experience |
| `correction` | 46 | Corrections to wrong assumptions or actions |

### Skills

**Internal taxonomy**: Ultron defines **39** categories in **9** groups (development and engineering, AI and data, automation and integration, daily life, productivity and knowledge, vertical industries, platforms, security, source types). **182** internal skills have been crystallized so far, triggered when a memory first enters HOT.

**External catalog** ([ModelScope Skill Hub](https://www.modelscope.cn/skills)): **30,000** indexed skills, by category:

| Category | Count |
|----------|-------|
| Dev tools | 11,415 |
| Code quality | 6,696 |
| Media | 2,938 |
| Frontend | 2,530 |
| Skills management | 1,805 |
| Marketing | 1,732 |
| Cloud efficiency | 1,640 |
| Mobile | 448 |
| Other | 796 |

Internal and catalog skills are searched through the same `/skills/search` endpoint and installed with `/skills/install` into a target directory.

## Further reading

- [Configuration](../Components/Config.md)
- [Memory Hub](../Components/MemoryHub.md)
- [Skill Hub](../Components/SkillHub.md)
- [Harness Hub](../Components/HarnessHub.md)
- [HTTP API reference](../API/HttpAPI.md)
- [Python SDK reference](../API/SDK.md)
