---
slug: HarnessHub
title: Harness Hub
description: Personal workspace sync and share across Claw products
---

# HarnessHub (personal config sync)

HarnessHub is Ultron’s module for syncing and sharing personal workspaces across Claw products (nanobot, openclaw, hermes, …): memories, skills, and persona files in one place.

## Concepts

| Concept | Description |
|---------|-------------|
| **user_id** | Stable user identifier |
| **agent_id** | Device or terminal id; one user can have many |
| **Claw** | A `(user_id, agent_id)` pair: one agent instance on one device |
| **Profile** | Server-side workspace snapshot: `resources` maps relative paths to text; `product` and other fields live in separate columns |
| **Allowlist** | Per-product glob list of files safe to sync (excludes sensitive files such as `.env`, `auth.json`) |
| **Bundle** | JSON package of workspace files for transport and storage |
| **Share token** | Share link credential; others can import your agent setup with a token or short code |

## Sync model

- Sync only happens between **the same `(user_id, agent_id)`** cloud profile and local disk
- **No automatic sync** across different devices
- Users manage multiple `agent_id` values in the Dashboard
- Synced content is workspace files (persona, memory, skills), **not** chat logs

```
Local workspace ──sync up──▶ Ultron server ──sync down──▶ local workspace
     │                        │
     │                        ▼
     │                  Share short code (6 chars)
     │                        │
     │              curl server/i/{code} | bash
     │                        │
     └────────────────────────┘
```

## Supported Claw products

| Product | Workspace path | Synced files |
|---------|----------------|--------------|
| nanobot | `~/.nanobot/workspace/` | AGENTS.md, SOUL.md, USER.md, TOOLS.md, HEARTBEAT.md, memory/*.md, skills/*/* |
| openclaw | `~/.openclaw/workspace/` | AGENTS.md, SOUL.md, USER.md, TOOLS.md, HEARTBEAT.md, memory/*.md, skills/*/* |
| hermes | `~/.hermes/` | config.yaml, SOUL.md, memories/*.md, skills/*/* |

All products **exclude**: `.env`, `auth.json`, `sessions/`, `logs/`, hidden files.

## Share flow

1. User A runs `sync up` to upload the workspace to Ultron
2. User A calls `create share` to get a short code (6 alphanumeric characters)
3. User A sends the code to user B
4. User B runs one line in the terminal to import:

```bash
curl -sL https://your-server/i/Ab3xK9 | bash
```

The server keeps **at most one** share per `(user_id, agent_id)`. After a share exists, each further **`sync up`** makes **HarnessService** refresh that share’s snapshot from the current profile (short code usually unchanged), so the next `curl … | bash` run gets the **latest** workspace. Copies already imported on a recipient machine are **not** updated automatically.

```
Local workspace ──sync up──▶ Ultron server ──create share──▶ short code Ab3xK9
                                                            │
                                                            ▼
                              curl -sL server/i/Ab3xK9 | bash
                                                            │
                                                            ▼
                                                     Local workspace
```

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Nanobot   │     │  OpenClaw   │     │   Hermes    │
│  Allowlist  │     │  Allowlist  │     │  Allowlist  │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────┬───────┘───────────────────┘
                   ▼
            HarnessBundle
                   │
                   ▼
          ┌────────────────┐
          │ HarnessService │
          └───────┬────────┘
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
   agents     profiles   shares
   (SQLite)   (SQLite)   (SQLite)
```

## Terminal import and recovery

Import is done by the **server** `GET /i/{short_code}` install script; locally you only need `curl` and `bash`, **not** a separate Python CLI:

```bash
curl -fsSL https://your-server/i/<short_code>?product=nanobot | bash
```

Before overwriting, the script backs up any existing workspace under `~/.ultron/harness-import-backups/` and prints `rm` / `mkdir` / `cp` commands to restore from that backup.

- In an **interactive TTY** (stdin is a TTY), the script prompts before continuing; in a **non-interactive** context (e.g. piped stdin) it continues immediately but still backs up non-empty workspaces.
- If the snapshot contains `skills/.ultron_modelscope_imports.json` (a JSON array; elements may include `full_name`), the script runs `modelscope skills add` for each skill before writing files, then copies into the workspace under `skills/<name>/`. The script exits with an error if the `modelscope` CLI is missing.
- Query param `product` may differ from the product in the snapshot; the server then uses `merge_resources` for cross-product merge (with each product’s default files).

Use the **Dashboard** or the HTTP API below for upload, download, and share creation.

## HTTP API overview

Unless stated otherwise, Harness **writes and sensitive reads** require JWT (see **Authentication** at the end). The following matches `ultron/api/routers/harness.py`.

### JWT required

| Endpoint | Description |
|----------|-------------|
| `GET /harness/agents` | List devices/agents for the current user |
| `DELETE /harness/agents` | Delete an `agent_id` (cascades profile and share) |
| `POST /harness/sync/up` | Upload workspace resources (body: `agent_id`, `product`, `resources`) |
| `POST /harness/sync/down` | Fetch profile by `agent_id` |
| `GET /harness/profile?agent_id=…` | Full profile for one agent |
| `GET /harness/profiles` | Profile summaries per `agent_id` for the current user |
| `POST /harness/share` | Create or refresh share (400 if no profile) |
| `GET /harness/shares` | List shares for the current user |
| `DELETE /harness/share` | Delete share by `token` |
| `POST /harness/soul-presets/build` | Merge presets into `resources` (body: `preset_ids` array) |

### No JWT

| Endpoint | Description |
|----------|-------------|
| `GET /harness/defaults/{product}` | Default workspace files per product |
| `GET /harness/soul-presets` | List presets by category |
| `GET /harness/soul-presets/{preset_id}` | One preset |
| `GET /harness/showcase` | `lang` query: `zh` / `en` |
| `GET /harness/showcase/{slug}` | One showcase entry |
| `GET /harness/share/export/{token}` | Same shell installer as short-code export (`product` can override target product) |
| `GET /i/{short_code}` | Installer by 6-character short code (`product` query optional) |

For full request bodies and response fields, see [HTTP API](../API/HttpAPI.md) and [Python SDK](../API/SDK.md).

## Extending to a new product

To add support for another Claw product:

1. Subclass `ClawWorkspaceAllowlist` in `ultron/services/harness/allowlist.py`
2. Define `product_name`, `workspace_root`, `patterns`
3. Register it in `ALLOWLIST_REGISTRY`

```python
class MyProductAllowlist(ClawWorkspaceAllowlist):
    @property
    def product_name(self) -> str:
        return "myproduct"

    @property
    def workspace_root(self) -> Path:
        return Path.home() / ".myproduct"

    @property
    def patterns(self) -> List[str]:
        return ["config.yaml", "SOUL.md", "memory/*.md"]

ALLOWLIST_REGISTRY["myproduct"] = MyProductAllowlist
```

## Per-product file patterns

### nanobot

| Pattern | Description |
|---------|-------------|
| `AGENTS.md` | Agent instructions |
| `SOUL.md` | Persona |
| `USER.md` | User profile |
| `TOOLS.md` | Tool definitions |
| `HEARTBEAT.md` | Scheduled tasks |
| `memory/MEMORY.md` | Long-term memory |
| `memory/HISTORY.md` | Session history |
| `skills/*/SKILL.md` | Skill definition |
| `skills/*/_meta.json` | Skill metadata |
| `skills/*/scripts/*` | Skill scripts |
| `skills/*/setup.md` | Skill setup doc |
| `skills/*/operations.md` | Skill operations doc |
| `skills/*/boundaries.md` | Skill boundaries doc |

### openclaw

Same as nanobot (shared workspace layout).

### hermes

| Pattern | Description |
|---------|-------------|
| `config.yaml` | Agent config |
| `SOUL.md` | Persona |
| `memories/*.md` | Memory files |
| `skills/*/SKILL.md` | Skill definition |
| `skills/*/_meta.json` | Skill metadata |
| `skills/*/scripts/*` | Skill scripts |

## Storage and bundle formats

**Profile (table `harness_profiles`)**

- `resources_json`: JSON object of **path → text only**, e.g. `{"SOUL.md": "…", "memory/MEMORY.md": "…"}`.
- `product`, `revision`, `updated_at`, etc. are table columns, not inside `resources_json`.

**Share (table `harness_shares`)**

- `snapshot_json`: server writes `{"product": "<product name>", "resources": { … }}`, generated or updated by `HarnessService` on `sync up` / `create share`. There is **no** `collected_at` field.

**`HarnessBundle` in code (`ultron/services/harness/bundle.py`)**

- Client-side wrapper when collecting from an allowlist; holds `product`, `resources`, and optional `collected_at`. `to_snapshot_json()` may emit JSON that includes `collected_at`; that shape need not match persisted `snapshot_json` in the database.

## Known limitations

- No binary files (text sync only)
- Max 1 MB per file (see `allowlist.MAX_FILE_SIZE`)
- An existing share may be **overwritten** on later `sync up` (see **Share flow** above); files already imported on the recipient machine are not auto-synced
- No conflict resolution: last `sync up` wins

See the HarnessHub sections in [HTTP API](../API/HttpAPI.md) and [Python SDK](../API/SDK.md).

---

## Authentication

Most Harness sync and share-management endpoints require JWT. **Public** endpoints (defaults, soul-presets list and detail, showcase, `GET /i/{short_code}`, `GET /harness/share/export/{token}`) do not require a token. Obtain a token via `POST /auth/register` or `POST /auth/login`, then pass `Authorization: Bearer <token>` on protected requests. `user_id` is taken from the token; you do not pass it explicitly.

See [HTTP API — Authentication](../API/HttpAPI.md#authentication).

---

## Soul Presets

Soul Presets ship ready-made agent personas. Each preset contains persona text split into workspace files (`SOUL.md`, `AGENTS.md`, `IDENTITY.md`) following the OpenClaw convention.

### Structure

- Presets live under `data/soul_presets/` with YAML frontmatter (`name`, `description`, `emoji`, `color`, `vibe`)
- Organized into 17 categories (creative, professional, technical, …)
- Over 200 built-in presets

### Build flow

1. User selects one or more preset IDs
2. `POST /harness/soul-presets/build` merges the selection
3. Response includes `{resources: {"SOUL.md": "...", "AGENTS.md": "...", "IDENTITY.md": "..."}}`
4. Client writes resources into the local workspace

### API

`GET` endpoints are public; `POST /harness/soul-presets/build` requires JWT (see **HTTP API overview**).

| Endpoint | Description |
|----------|-------------|
| `GET /harness/soul-presets` | List all presets by category |
| `GET /harness/soul-presets/{preset_id}` | Full preset including body |
| `POST /harness/soul-presets/build` | Build merged resources from selected presets |

---

## Showcase

Showcase lists curated agent examples with multilingual support.

### Structure

- Markdown files under `docs/{lang}/Showcase/` (`zh` and `en` supported)
- YAML frontmatter: `name`, `description`, `emoji`, `short_code`, `agent_id`, `tags`
- Each entry has a unique slug derived from the filename

### API

| Endpoint | Description |
|----------|-------------|
| `GET /harness/showcase?lang=en` | List all entries for a language |
| `GET /harness/showcase/{slug}?lang=en` | Full showcase content |

---

## Defaults (product default files)

Each supported product includes default workspace files so new users can start quickly.

| Product | Default files |
|---------|---------------|
| nanobot | SOUL.md, AGENTS.md, USER.md, TOOLS.md, HEARTBEAT.md |
| openclaw | SOUL.md, AGENTS.md, USER.md, TOOLS.md, HEARTBEAT.md |
| hermes | config.yaml, SOUL.md |

### API

```
GET /harness/defaults/{product}
```

Returns `{success, product, files}` where `files` maps filenames to contents.
