---
slug: HttpAPI
title: HTTP API
description: Ultron HTTP API reference
---

# HTTP API

Ultron exposes a RESTful HTTP API on FastAPI, default base `http://0.0.0.0:9999`.

## Run the server

```shell
uvicorn ultron.server:app --host 0.0.0.0 --port 9999
```

## General notes

- **Responses**: JSON
- **Background jobs**: After startup the process runs memory decay on `decay_interval_hours` (tier rebalance and related work); if `async_embedding=true`, an embedding queue worker shares the same `Ultron` instance as HTTP

---

## System

### Health check

```
GET /
```

Redirects to `/dashboard` (HTTP 302).

```
GET /health
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

### System stats

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

## Memory (Remote Memory)

### Upload memory

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

### Search memories

```
POST /memory/search
```

**Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | yes | Natural-language query |
| `tier` | string | no | `hot` / `warm` / `cold` to restrict one tier; `all` for every tier; **omit or `null`** searches all tiers |
| `limit` | int | no | Max hits; **omit** → server `ULTRON_MEMORY_SEARCH_LIMIT` (default **10**) |
| `detail_level` | string | no | **`l0`** or **`l1`** (default `l0`). Only affects whether body-like fields are truncated or cleared: `l0` is summary-oriented (often `summary_l0`); `l1` keeps more context fields |

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

### Memory details

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

### Unified ingestion

```
POST /ingest
{
    "paths": ["/path/to/file.txt", "/path/to/sessions/"]
}
```

- **`success`**: `true` when `data.successful > 0`
- **`data`**: Raw smart-ingestion result (paths processed, counts, etc.; exact keys depend on runtime)

### Text ingestion

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

### Install skill to directory

```
POST /skills/install
```

Installs into a target directory. Resolves internal slug first; otherwise `modelscope skill add` from ModelScope Skill Hub for catalog skills.

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
GET /harness/agents
```

Requires `Authorization: Bearer <token>`.

**Response:**

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

Requires `Authorization: Bearer <token>`.

**Body:**

| Field | Type | Required |
|-------|------|----------|
| `agent_id` | string | yes |

Deletes the agent’s profile and share tokens.

### Sync up (upload workspace)

```
POST /harness/sync/up
```

Requires `Authorization: Bearer <token>`.

**Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
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

### Sync down (download workspace)

```
POST /harness/sync/down
```

Requires `Authorization: Bearer <token>`.

**Body:**

| Field | Type | Required |
|-------|------|----------|
| `agent_id` | string | yes |

404 if no profile exists.

### Get profile

```
GET /harness/profile?agent_id=d1
```

Requires `Authorization: Bearer <token>`.

### Get all profiles

```
GET /harness/profiles
```

Requires `Authorization: Bearer <token>`. Returns all profiles for the authenticated user.

### Create share

```
POST /harness/share
```

Requires `Authorization: Bearer <token>`.

**Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `agent_id` | string | yes | Device id |
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

### List shares

```
GET /harness/shares
```

Requires `Authorization: Bearer <token>`.

### Delete share

```
DELETE /harness/share
```

Requires `Authorization: Bearer <token>`.

**Body:**

| Field | Type | Required |
|-------|------|----------|
| `token` | string | yes |

### Export share

```
GET /harness/share/export/{token}
```

Returns a bash install script for the shared agent configuration.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `token` | path | string | yes | Share token |
| `product` | query | string | no | Target product (default `nanobot`) |

### Short code import

```
GET /i/{code}
```

Short-code alias for share export. Returns a bash install script.

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `code` | path | string | yes | 6-char short code |
| `product` | query | string | no | Target product (default `nanobot`) |

### Product defaults

```
GET /harness/defaults/{product}
```

Returns default workspace files for a product (`nanobot`, `openclaw`, `hermes`).

**Response:**

```json
{
    "success": true,
    "product": "nanobot",
    "files": {"SOUL.md": "...", "AGENTS.md": "..."}
}
```

---

## Authentication

### Register

```
POST /auth/register
```

**Body:**

| Field | Type | Required |
|-------|------|----------|
| `username` | string | yes |
| `password` | string | yes |

**Response:**

```json
{
    "success": true,
    "data": {
        "username": "alice",
        "token": "eyJ..."
    }
}
```

### Login

```
POST /auth/login
```

**Body:**

| Field | Type | Required |
|-------|------|----------|
| `username` | string | yes |
| `password` | string | yes |

**Response:**

```json
{
    "success": true,
    "data": {
        "username": "alice",
        "token": "eyJ..."
    }
}
```

### Current user

```
GET /auth/me
```

Requires `Authorization: Bearer <token>`.

**Response:**

```json
{
    "success": true,
    "data": {
        "username": "alice",
        "created_at": "2026-04-06T12:00:00"
    }
}
```

---

## Soul Presets (role presets)

### List presets

```
GET /harness/soul-presets
```

Returns all presets grouped by category.

**Response:**

```json
{
    "success": true,
    "data": {
        "categories": [
            {
                "category": "creative",
                "presets": [{"id": "poet", "name": "Poet", "emoji": "✍️", "description": "..."}]
            }
        ]
    }
}
```

### Get preset

```
GET /harness/soul-presets/{preset_id}
```

Returns full preset details including body content.

### Build role resources

```
POST /harness/soul-presets/build
```

Builds merged workspace resources from selected presets. The body is split into `SOUL.md`, `AGENTS.md`, and `IDENTITY.md`.

**Body:**

```json
{
    "preset_ids": ["poet", "mentor"]
}
```

**Response:**

```json
{
    "success": true,
    "data": {
        "resources": {
            "SOUL.md": "...",
            "AGENTS.md": "...",
            "IDENTITY.md": "..."
        }
    }
}
```

---

## Showcase (examples)

### List showcases

```
GET /harness/showcase?lang=en
```

| Parameter | In | Type | Required | Description |
|-----------|-----|------|----------|-------------|
| `lang` | query | string | no | `zh` or `en` (default `zh`) |

### Get showcase

```
GET /harness/showcase/{slug}?lang=en
```

Returns full showcase entry by slug.

---

## Dashboard (control panel)

### Dashboard UI

```
GET /dashboard
```

Returns the dashboard HTML page. SPA routes (`/skills`, `/leaderboard`, `/quickstart`, `/harness`) also serve the same HTML.

### Overview

```
GET /dashboard/overview
```

```json
{
    "memory": {...},
    "skills": {...}
}
```

### List memories

```
GET /dashboard/memories?q=docker&memory_type=error&tier=hot&sort=recent&page=1&page_size=20
```

All query parameters are optional. Returns paginated memory list.

### List skills

```
GET /dashboard/skills?q=python&source=internal&category=ai&page=1&page_size=20
```

All query parameters are optional. Returns paginated skill list.

### Skill markdown

```
GET /dashboard/skills/internal/{slug}/skill-md
```

Returns the raw SKILL.md content for an internal skill.

```json
{
    "slug": "my-skill",
    "content": "# My Skill\n..."
}
```

### Leaderboard

```
GET /dashboard/leaderboard?limit=20
```

Returns skill usage leaderboard data.

### Agent skill package

```
GET /dashboard/agent-skill-package
```

Returns a ZIP file containing all skills for agent deployment.

---

## HTTP status codes

| HTTP status | Description |
|-------------|-------------|
| 200 | Success |
| 400 | Bad request parameters |
| 403 | Insufficient permission |
| 404 | Resource not found (e.g. skill missing) |
| 422 | Request body validation failed (FastAPI) |
| 500 | Internal server error |

---

## Request tracing

Each request is assigned a unique `trace_id`:

- Response header: `X-Trace-Id: a1b2c3d4e5f6`
- Use this id to follow the full request path in logs

## CORS

By default all origins are allowed (`allow_origins=["*"]`). In production, restrict to specific domains.
