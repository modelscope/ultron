---
slug: TrajectoryHub
title: Trajectory Hub
description: "Ultron (奥创): session capture, task segmentation, trajectory metrics, delayed memory extraction, and SFT export"
---

# Trajectory Hub

The Trajectory Hub handles **session capture and intelligent processing**: uploaded `.jsonl` files are split by the LLM into independent **task segments**, then `ms_agent.trajectory` scores each segment. Only segments that meet the metric thresholds are selected for memory extraction or SFT-style export.

---

## Task Segmentation

A single `.jsonl` session may cover **several different tasks** in one conversation. The Trajectory Hub uses an LLM to cut the conversation into independent **task segments**; scoring, memory extraction, and SFT export all run at **segment** granularity.

### Core Concepts

| Concept | Description |
|---------|-------------|
| **Task Segment** | An independent task slice within a conversation; boundaries identified by LLM |
| **Content Fingerprint** | SHA-256 hash (16 hex chars) of segment message content; used for incremental tracking |
| **Segment-level Pipeline** | Metric analysis, memory extraction, and SFT export all operate per segment |

### Segmentation and Incremental Rules

1. **LLM segmentation** (long conversations may use **multiple** model rounds; each round only sees one **window** of messages):
   - **Each round**: within the user-text token budget, pack as many messages as possible from the **current** start; the model only uses **in-window** indices `1…L` to output one or more tasks.
   - **Multiple tasks** this round: the **next** window starts at the **first message of the last task** from this round, then packs forward to the budget again; the slice that overlaps a previous round is **replaced** by the new result (remove old segments from that start forward, then append the new one).
   - **Exactly one task** this round and it fills the window, with more messages after: the **next** window starts at the first message **after** this window (**no** overlap).
   - If a **single** message still exceeds the budget, it is only truncated in a **one-message** window. `role: tool` rows with empty name, id, and **content** are **kept** so line indices stay aligned with the source JSONL (display may show an empty line).
   - **Example** (indices 1-based):
     - First window 1–6 → tasks A = 1–3, B = 4–6. Next window starts at **4** (e.g. 4–10); B may be refined to 4–7 and C = 8–10 added; the saved B comes from the **second** run.
     - If the first window 1–6 is a **single** task 1–6, the next window starts at **7** (no overlap).
2. **Fingerprinting**: per segment, SHA-256 over messages (`role` + `content`).
3. **Incremental comparison**:
   - Fingerprint **matches** an existing segment → **skip** (idempotent).
   - Fingerprint **mismatches** (e.g. file appended; task C went from partial to complete) → archive memories for the old segment via `segment:{id}`, delete the old row, insert the new segment.
4. **Short chats**: if there are **≤ 2** messages, one segment is created **without** calling the LLM.
5. **LLM unavailable**: skip segmentation; session stays `segmented=0` and is retried on the next run.

### Incremental Tracking Example

```
Day 1: file.jsonl contains tasks A, B, C (partial)
  → LLM segmentation → [A(fp=x), B(fp=y), C_partial(fp=z1)]
  → Each independently metric-scored → eligible segments extract memory (with segment:{id[:8]} tag)

Day 2: file.jsonl appended; C is now complete
  → Re-run LLM segmentation → [A(fp=x), B(fp=y), C_complete(fp=z2)]
  → A skipped (fp=x matches) → B skipped (fp=y matches)
  → C: old z1 memories archived, old segment deleted, new z2 re-scored and re-extracted if eligible
```

---

## End-to-End Flow

```
[Ingest]
Export conversation as .jsonl → POST /ingest (requires agent_id)
  → Persist session row (segmented=0) → segmentation runs **asynchronously** in the scheduled job

[Scheduled job (interval: decay_interval_hours)]
1. segment_pending_sessions()
     → Fetch sessions with segmented=0 → read file → LLM task segmentation
     → Success → save task_segments (fingerprint dedup), mark segmented=1
     → ≤ 2 messages → create single segment, mark segmented=1
     → LLM unavailable → skip, keep segmented=0, retry next cycle

2. label_pending_segments()
     → ms_agent.trajectory writes the full analysis JSON to `quality_metrics` (`summary.overall_score`, `summary.task_type`, etc.), labeled=1
     → If ms-agent trajectory analysis is unavailable: skip, keep labeled=0, retry next cycle

3. extract_memories_from_segments()
     → Coarse filter on `summary.overall_score` (0–1) from `quality_metrics`, `memory_extracted=0`, and passing `is_memory_eligible`
     → Read message range → MemoryService.upload_memory
     → Each memory tagged segment:{id[:8]} → memory_extracted=1

4. tier rebalance → skill evolution → consolidation (if enabled)
```

---

## Database Tables

### `task_segments`

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | UUID |
| `agent_id` | TEXT NOT NULL | Maps to ingest `agent_id` |
| `session_file` | TEXT NOT NULL | Source file absolute path |
| `segment_index` | INTEGER NOT NULL | Order within the file (0-based) |
| `start_line` | INTEGER NOT NULL | Start line (1-based inclusive) |
| `end_line` | INTEGER NOT NULL | End line (1-based inclusive) |
| `fingerprint` | TEXT NOT NULL | SHA-256 content fingerprint (16 hex chars) |
| `topic` | TEXT | LLM-generated task topic summary |
| `quality_metrics` | TEXT | Full `ms_agent.trajectory` analysis JSON; **`summary.overall_score` (0–1), `summary.task_type`, and other fields are only stored in this column** (not duplicated elsewhere); derive fields in queries and APIs from this JSON when needed |
| `labeled` | INTEGER | 0=pending, 1=labeled |
| `memory_extracted` | INTEGER | 0=not extracted, 1=extracted |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Update time |

**Unique constraint**: `UNIQUE(agent_id, session_file, fingerprint)` — prevents duplicate segments with the same fingerprint within the same file.

### `trajectory_records` (Session Metadata)

Stores session-level metadata (one row per `.jsonl` file, `pair_index=-1`) for tracking segmentation status.

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | UUID |
| `source_agent_id` | TEXT | Maps to ingest `agent_id` |
| `session_file` | TEXT | Source file absolute path |
| `segmented` | INTEGER | 0=not segmented, 1=segmented |
| `created_at` | TIMESTAMP | Creation time |

---

## `.jsonl` Format

One JSON object per line. Parsing is in `ultron/utils/jsonl_session_messages.py`. Sessions are **agent** conversations with roles `user` / `assistant` / `system` / `tool`; **skip** `_type == "metadata"`. OpenAI- and Anthropic-style lines are supported; default `session_format="auto"`. After parsing, `filter_messages_for_trajectory` drops rows that expand to empty LLM text; `assistant` can remain with only `tool_calls` / `reasoning_content`.

```jsonl
{"role": "user", "content": "How do I read a CSV in Python?"}
{"role": "assistant", "content": "You can use pandas.read_csv()..."}
{"role": "user", "content": "Write me a Docker compose file"}
{"role": "assistant", "content": "version: '3'\nservices:\n  ..."}
```

After segmentation, this example becomes two task segments: CSV and Docker compose.

---

## Content Fingerprint

The fingerprint is computed from each message's `role` and `content` fields using SHA-256, truncated to the first 16 hex characters.

```python
def compute_segment_fingerprint(messages: List[dict]) -> str:
    hasher = hashlib.sha256()
    for msg in messages:
        hasher.update((msg.get("role") or "").encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update((msg.get("content") or "").encode("utf-8"))
        hasher.update(b"\x01")
    return hasher.hexdigest()[:16]
```

Key roles of the fingerprint:
- **Idempotency**: Re-uploading the same file skips segments whose fingerprints already exist
- **Change detection**: When a file is appended and a segment's content changes, the old fingerprint won't match, triggering memory archival and re-processing
- **Replaces line-number cursor**: No longer relies on line offsets for incremental tracking, preventing task tearing on file appends

---

## Memory Invalidation

When a segment's content changes (fingerprint mismatch):

1. `archive_memories_by_tag("segment:{old_id[:8]}")` marks the old segment's memories as `archived`
2. The old segment record is deleted
3. A new segment is inserted; the scheduled job will re-score and re-extract if eligible

This ensures memories always reflect the segment's latest content.

---

## Trajectory Metrics

`label_pending_segments()` imports `ms_agent.trajectory` from the installed `ms_agent` package, injects Ultron's configured `quality_llm` as the metric model, and stores output **only** in `quality_metrics`; coarse filters and `is_memory_eligible` read `summary` / `metrics` from that JSON.

| Threshold | Default | Purpose |
|-----------|---------|---------|
| `ULTRON_TRAJECTORY_MEMORY_SCORE_THRESHOLD` | `0.7` | Coarse filter floor for memory (0–1) |
| `ULTRON_TRAJECTORY_SFT_SCORE_THRESHOLD` | `0.8` | Coarse filter floor for SFT export / training (0–1) |

---

## SDK Usage (Python)

```python
from ultron import Ultron

u = Ultron()

# Stats (includes segments sub-dict)
stats = u.trajectory_service.get_trajectory_stats()
# stats["segments"] = {"total": 15, "labeled": 10, "memory_eligible": 8, "sft_eligible": 6, "memory_extracted": 6}

# Manually trigger segmentation / labeling / extraction (normally run by `run_decay_loop` in `ultron/services/background.py`)
u.trajectory_service.segment_pending_sessions(batch_size=50)
u.trajectory_service.label_pending_segments(batch_size=50)
u.trajectory_service.extract_memories_from_segments(batch_size=50)

# SFT-style export: segments above the score threshold, optional task_type filter
dataset = u.trajectory_service.export_sft(task_type="code", min_quality_score=0.8, limit=5000)
# [{"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}], "topic": "..."}, ...]
```

---

## Source Code

`TrajectoryService` is the public facade; it composes session reads, segmentation, labeling, the trajectory→memory bridge, and SFT export. SFT training is under `services/training/`, decoupled from capture.

| Module | Path |
|--------|------|
| Segment & session metadata tables | `ultron/core/db_trajectory.py` |
| Trajectory facade (stable public API) | `ultron/services/trajectory/trajectory_service.py` |
| Session file + segment message reads | `ultron/services/trajectory/session_reader.py` — `TrajectorySessionReader` |
| Task segmentation | `ultron/services/trajectory/segmenter.py` — `TrajectorySegmenter` |
| Metric labeling | `ultron/services/trajectory/labeler.py` — `TrajectoryLabeler` |
| Trajectory → memory extraction & upload | `ultron/services/memory/trajectory_extractor.py` — `TrajectoryMemoryExtractor` |
| SFT export & Twinkle message formatting | `ultron/services/training/sft_exporter.py` — `SFTExporter` |
| SFT self-training (Twinkle) | `ultron/services/training/sft_trainer.py` — `SFTTrainerService` |
| Background job orchestration (segment→label→memory→rebalance→…) | `ultron/services/background.py` — `run_decay_loop`; started from `server.py` lifespan |
| Trajectory metrics | `ms_agent.trajectory` — `analyze_trajectory` |
| Task split (LLM) | `ultron/utils/llm_orchestrator.py` — `segment_conversation_tasks` |
| Content fingerprint | `ultron/utils/token_budget.py` — `compute_segment_fingerprint` |
| `.jsonl` ingest | `ultron/services/ingestion.py` — `_ingest_jsonl_trajectories` |
| Memory archive by tag | `ultron/core/db_memory.py` — `archive_memories_by_tag` |

For more on memory, see [Memory Hub](MemoryHub.md).
