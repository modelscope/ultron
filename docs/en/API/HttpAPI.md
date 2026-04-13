---
slug: HttpAPI
title: HTTP API
description: Ultron REST API reference
---

# HTTP API

Ultron exposes a REST API on FastAPI, default base `http://0.0.0.0:9999`.

## Run the server

```shell
uvicorn ultron.server:app --host 0.0.0.0 --port 9999
```

## General

- **Responses**: JSON
- **Background**: Memory decay runs on `decay_interval_hours`; if `async_embedding=true`, an embedding worker shares the same `Ultron` instance as HTTP

---

## System

### Health

```
GET /
```

**Response:**

```json
{
    "status": "ok",
    "service": "ultron",
    "version": "1.0.0",
    "architecture": "collective-intelligence"
}
```

### Stats

```
GET /stats
```

Aggregates **skill storage**, **skill categories**, **embedding service**, and **memory store**.

**Example shape:**

```json
{
  "storage": {
    "total_skills": 56,
    "archived_skills": 2,
    "total_size_bytes": 1048576,
    "total_size_mb": 1.0,
    "skills_dir": "/path/to/skills",
    "archive_dir": "/path/to/archive"
  },
  "categories": {
    "total_skills": 56,
    "total_categories": 120,
    "categories_with_skills": 45,
    "dimension_stats": {},
    "top_categories": [{"name": "ai-llms", "count": 8}]
  },
  "embedding": {
    "backend": "dashscope",
    "model_name": "text-embedding-v4",
    "dimension": 1024,
    "is_available": true,
    "has_dashscope": true,
    "has_numpy": true,
    "request_timeout_seconds": 600
  },
  "memory": {
    "total": 1234,
    "by_tier": {"hot": 40, "warm": 500, "cold": 694},
    "by_type": {"pattern": 800, "error": 400},
    "by_status": {"active": 1200}
  }
}
```

---

## Memory (remote memory)

### Upload

```
POST /memory/upload
```

**Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | string | yes | Memory body |
| `context` | string | no | Scenario |
| `resolution` | string | no | Fix or playbook |
| `tags` | string[] | no | Tags |

**Response:**

```json
{
    "success": true,
    "data": {
        "id": "mem-xxx",
        "memory_type": "error",
        "tier": "warm",
        "hit_count": 1,
        "status": "active"
    }
}
```

### Search

```
POST /memory/search
```

**Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | yes | Natural language |
| `tier` | string | no | `hot` / `warm` / `cold` / `all`; omit or `null` = all |
| `limit` | int | no | Max rows; omit → `ULTRON_MEMORY_SEARCH_LIMIT` (default **10**) |
| `detail_level` | string | no | **`l0`** or **`l1`** (default `l0`). Truncates or clears body fields; `l0` is summary-first; `l1` keeps more context |

**Response:**

```json
{
    "success": true,
    "count": 5,
    "data": [
        {
            "id": "mem-xxx",
            "memory_type": "error",
            "content": "",
            "context": "",
            "resolution": "",
            "summary_l0": "Handling missing pandas in Python",
            "overview_l1": "",
            "tier": "warm",
            "similarity_score": 0.8765,
            "tier_boosted_score": 1.0518
        }
    ]
}
```

### Details

```
POST /memory/details
{
    "memory_ids": ["mem-001", "mem-002", "mem-003"]
}
```

Returns readable `MemoryRecord` fields (full `content` / `context` / `resolution`, tags, summaries, timestamps).

```json
{
  "success": true,
  "count": 2,
  "data": [
    {
      "id": "mem-001",
      "memory_type": "error",
      "content": "full text ...",
      "context": "",
      "resolution": "",
      "tier": "warm",
      "hit_count": 3,
      "summary_l0": "",
      "overview_l1": ""
    }
  ]
}
```

### Memory stats

```
GET /memory/stats
```

```json
{
  "success": true,
  "data": {
    "total": 1234,
    "by_tier": { "hot": 40, "warm": 500, "cold": 694 },
    "by_type": { "pattern": 800 },
    "by_status": { "active": 1100 }
  }
}
```

---

## Sessions and ingestion

### Unified ingest

```
POST /ingest
{
    "paths": ["/path/to/file.txt", "/path/to/sessions/"]
}
```

- **`success`**: `true` when `data.successful > 0`
- **`data`**: Raw smart-ingestion result (paths processed, counts, etc.; exact keys depend on runtime)

### Text ingest

```
POST /ingest/text
{
    "text": "raw text..."
}
```

- **`success`**: from the ingest result `success` flag
- **`data`**: Details dict from `ingest_text`

---

## Skills (Skill Hub)

### List skills

```
GET /skills
```

```json
{
  "success": true,
  "count": 2,
  "data": [
    { "slug": "my-skill", "version": "1.0.0", "path": "/abs/path/to/my-skill-1.0.0" }
  ]
}
```

### Search skills

```
POST /skills/search
{
    "query": "how to fix Python import errors",
    "limit": 3
}
```

- **`limit`** omitted → `ULTRON_SKILL_SEARCH_LIMIT` (default **5**)

```json
{
  "success": true,
  "count": 2,
  "data": [
    {
      "slug": "fix-imports",
      "version": "1.0.0",
      "name": "Fix Imports",
      "description": "...",
      "categories": ["coding-agents-ides"],
      "similarity_score": 0.82,
      "combined_score": 0.91,
      "source": "internal",
      "full_name": null
    },
    {
      "slug": "catalog-skill-example",
      "version": "1.0.0",
      "name": "Catalog Skill Example",
      "description": "...",
      "categories": ["coding-agents-ides"],
      "similarity_score": 0.78,
      "combined_score": 0.85,
      "source": "catalog",
      "full_name": "@ns/catalog-skill-example"
    }
  ]
}
```

### Upload skills

```
POST /skills/upload
{
    "paths": ["/path/to/skill-dir", "/path/to/skills-folder"]
}
```

Directory rules: if the path contains `SKILL.md` at top level, it is one skill; if not, scan **one level** of subfolders that contain `SKILL.md`.

**Response:**

```json
{
    "success": true,
    "data": {
        "total": 2,
        "successful": 2,
        "results": [
            {"path": "/path/to/skill-dir", "success": true, "slug": "my-skill", "version": "1.0.0", "name": "My Skill"},
            {"path": "/path/to/skills-folder/sub-skill", "success": true, "slug": "sub-skill", "version": "1.0.0", "name": "Sub Skill"}
        ]
    }
}
```

**`success`**: `true` when `successful > 0`.

### Install skill

```
POST /skills/install
```

Installs into a target directory. Resolves internal slug first; otherwise `modelscope skill add` for catalog skills.

**Body:**

```json
{
    "full_name": "@ns/name",
    "target_dir": "~/.nanobot/workspace/skills"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `full_name` | string | yes | Catalog name like `@ns/name`, or internal slug |
| `target_dir` | string | yes | Destination directory |

**Response:**

```json
{
    "success": true,
    "full_name": "@ns/name",
    "source": "internal",
    "installed_path": "~/.nanobot/workspace/skills/@ns/name"
}
```

- `source`: `"internal"` or `"catalog"`

---

## Harness Hub (personal sync)

### List agents

```
GET /harness/agents?user_id=u1
```

```json
{
    "success": true,
    "count": 2,
    "data": [...]
}
```

### Delete agent

```
DELETE /harness/agents
```

**Body:**

| Field | Type | Required |
|-------|------|----------|
| `user_id` | string | yes |
| `agent_id` | string | yes |

Deletes the agent’s profile and share tokens.

### Sync up

```
POST /harness/sync/up
```

**Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_id` | string | yes | User id |
| `agent_id` | string | yes | Device id |
| `product` | string | no | Claw product (default `nanobot`) |
| `resources` | object | yes | Map of relative path → file text |

**Response:**

```json
{
    "success": true,
    "data": {
        "user_id": "u1",
        "agent_id": "d1",
        "revision": 1,
        "resources": {"SOUL.md": "..."},
        "product": "nanobot",
        "updated_at": "2026-04-06T12:00:00"
    }
}
```

### Sync down

```
POST /harness/sync/down
```

**Body:**

| Field | Type | Required |
|-------|------|----------|
| `user_id` | string | yes |
| `agent_id` | string | yes |

404 if no profile exists.

### Get profile

```
GET /harness/profile?user_id=u1&agent_id=d1
```

### Create share

```
POST /harness/share
```

**Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_id` | string | yes | Owner user |
| `agent_id` | string | yes | Owner device |
| `visibility` | string | no | `link` / `public` / `private` (default `link`) |

**Response:**

```json
{
    "success": true,
    "data": {
        "token": "abc123...",
        "source_user_id": "u1",
        "source_agent_id": "d1",
        "visibility": "link",
        "snapshot": {...},
        "created_at": "2026-04-06T12:00:00"
    }
}
```

### Import share

```
POST /harness/share/import
```

**Body:**

| Field | Type | Required |
|-------|------|----------|
| `token` | string | yes |
| `target_user_id` | string | yes |
| `target_agent_id` | string | yes |

Imports the snapshot as the target user’s profile.

### List shares

```
GET /harness/shares?user_id=u1
```

### Delete share

```
DELETE /harness/share
```

**Body:**

| Field | Type | Required |
|-------|------|----------|
| `token` | string | yes |

---

## HTTP status codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request |
| 403 | Forbidden |
| 404 | Not found (e.g. skill missing) |
| 422 | Validation error (FastAPI) |
| 500 | Server error |

---

## Tracing

Each request gets a `trace_id`:

- Response header: `X-Trace-Id: a1b2c3d4e5f6`
- Correlate logs with this id

## CORS

Default `allow_origins=["*"]`. Lock this down in production.
