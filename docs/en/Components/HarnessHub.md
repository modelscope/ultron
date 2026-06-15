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
| nanobot | `~/.nanobot/workspace/` | AGENTS.md, SOUL.md, USER.md, TOOLS.md, HEARTBEAT.md, agents/&lt;name&gt;.md, memory/*.md, skills/*/* |
| openclaw | `~/.openclaw/workspace/` (or `workspace-<name>`) | AGENTS.md, SOUL.md, USER.md, TOOLS.md, HEARTBEAT.md, IDENTITY.md, BOOTSTRAP.md, MEMORY.md, memory/*, skills/*/* |
| hermes | `~/.hermes/` | SOUL.md, memories/*.md, skills/*/* (incl. nested) |
| qwenpaw | `~/.qwenpaw/workspaces/<name>/` | AGENTS.md, SOUL.md, PROFILE.md, BOOTSTRAP.md, MEMORY.md, HEARTBEAT.md, memory/*.md, skills/*/* |
| openhuman | `~/.openhuman/workspace/` | SOUL.md, IDENTITY.md, USER.md, PROFILE.md, MEMORY.md, HEARTBEAT.md, wiki/*.md, skills/*/* |
| qoder | `~/.qoder/` (or a project's `.qoder/`) | AGENTS.md, agents/&lt;name&gt;.md, commands/*.md, rules/*.md, skills/*/* |

All products **exclude**: `.env`, `auth.json`, `sessions/`, `logs/`, hidden files.

The on-disk **sub-agent layout** differs by product — see the [`ultron upload` CLI](#cli-ultron-upload) section below for the per-framework table.

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

## CLI: `ultron upload`

The `ultron` command uploads a single sub-agent's files to the agent repository
without crafting any HTTP requests. Given a **framework** (bot type) and an
**internal sub-agent name**, it locates the files on disk (using the per-product
allowlist) and uploads them; the sub-agent name also becomes the repository name
(`agent_id`).

```bash
# 1. Authenticate once (token saved to ~/.ultron/cli.json)
ultron login --server http://localhost:9999 --username alice

# 2. Upload one sub-agent (auto-discovers files at the framework's default path)
ultron upload --framework qoder --name reviewer

# Preview without uploading, or point at a custom directory
ultron upload --framework qoder --name reviewer --dry-run
ultron upload --framework qwenpaw --name default --local_dir ~/.qwenpaw/workspaces/default

# List the sub-agents discovered on disk for a framework
ultron upload --framework qoder --list
```

On upload the CLI packs the sub-agent's whole directory into a single **zip** and
submits it via `POST /api/v1/files/upload` (`multipart/form-data`, fields `file`
plus `Path`/`Name`/`Framework`/`commit_message`). A whole-directory snapshot is
used instead of per-file commits because only a complete file set lets the server
derive **deletes** (which files were removed), not just updates.

### Download (with optional format conversion)

`ultron download` fetches a sub-agent's stored files and writes them into the
local workspace. The source framework is read from the repository, so usually
only `--name` is needed. Download is two steps: list files via
`GET /api/v1/agents/{path}/{name}/repo/files`, then resolve each file's download
link and fetch them one by one. Pass `--target` to **convert** the files into
another framework's format on the way down (e.g. you stored an openclaw agent but
want to run it under qwenpaw):

```bash
# Restore into the source framework's workspace
ultron download --name reviewer

# Convert openclaw -> qwenpaw and write to qwenpaw's workspace
ultron download --name reviewer --target qwenpaw

# Preview, or write somewhere else
ultron download --name reviewer --target qwenpaw --dry-run
ultron download --name reviewer --local_dir /tmp/restore
```

### Convert locally (no upload/download)

`ultron convert` runs the same cross-framework migration **entirely on local
files** — nothing is uploaded or downloaded. It reads the source framework's
workspace, converts it to the target format, and writes the result (to the
target framework's workspace by default, or `--out`):

```bash
ultron convert --from nanobot --to hermes
ultron convert --from openclaw --to qwenpaw --local_dir ~/.openclaw/workspace --out /tmp/qwenpaw-ws
ultron convert --from nanobot --to openhuman --dry-run
```

Conversion is powered by the same engine as the server's cross-product import
(`merge_resources` in `ultron/services/harness/merge.py`): semantically
equivalent files are remapped to the target's paths (e.g. nanobot `USER.md` →
hermes `memories/USER.md`) and merged with the target's default templates. The
five persona products (nanobot, openclaw, hermes, qwenpaw, openhuman) convert
cleanly between each other; `qoder` has no semantic mapping yet, so its
agent/command/rule files are carried over verbatim.

`ULTRON_SERVER` / `ULTRON_TOKEN` override the stored credentials (handy in CI).

A framework may host several sub-agents; the CLI uploads **one at a time** and
collects the selected sub-agent's own file **plus shared resources** (skills,
rules, commands, `AGENTS.md`). Layouts per framework:

| Framework | Layout | Sub-agent `<name>` location |
|-----------|--------|-----------------------------|
| qwenpaw | root-per-agent | `~/.qwenpaw/workspaces/<name>` |
| openclaw | root-per-agent | `~/.openclaw/workspace` (default) / `workspace-<name>` |
| qoder | file-per-agent + shared | `~/.qoder/agents/<name>.md` + shared `skills/`, `rules/`, `commands/`, `AGENTS.md` |
| nanobot | file-per-agent + shared | `~/.nanobot/workspace/agents/<name>.md` + shared persona/memory/skills |
| hermes | single-agent | `~/.hermes/` (name is just the repo identity) |
| openhuman | single-agent | `~/.openhuman/workspace/` (name is just the repo identity) |

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
2. Define `product_name`, `default_workspace_root`, `patterns`
3. (Optional) override `list_agents()` for multi-sub-agent discovery
4. Register it in `ALLOWLIST_REGISTRY`

The base class is **sub-agent-aware**: the constructor takes `agent_name` (the
selected sub-agent) and an optional `local_dir` override. `default_workspace_root`
may embed `self.agent_name` (root-per-agent products), and any `{name}`
placeholder in `patterns` is formatted with it so only the selected sub-agent's
file matches (file-per-agent products). Single-agent products simply ignore it.

```python
class MyProductAllowlist(ClawWorkspaceAllowlist):
    @property
    def product_name(self) -> str:
        return "myproduct"

    @property
    def default_workspace_root(self) -> Path:
        # root-per-agent: embed the sub-agent name; or a fixed path for single-agent
        return Path.home() / ".myproduct" / "agents" / self.agent_name

    @property
    def patterns(self) -> List[str]:
        # file-per-agent example: "{name}" is replaced with the sub-agent name
        return ["SOUL.md", "memory/*.md", "agents/{name}.md"]

ALLOWLIST_REGISTRY["myproduct"] = MyProductAllowlist
```

`collect()` returns `{workspace_relative_path: text}` regardless of the layout,
so the server, `merge.py`, and the dashboard all share one key space. The
dashboard mirrors this logic in TypeScript
(`ultron/dashboard/src/components/harness/UploadWorkspace.tsx`) — keep both in sync.

## Per-product file patterns

### nanobot

| Pattern | Description |
|---------|-------------|
| `AGENTS.md` | Agent instructions |
| `SOUL.md` | Persona |
| `USER.md` | User profile |
| `TOOLS.md` | Tool definitions |
| `HEARTBEAT.md` | Scheduled tasks |
| `agents/{name}.md` | Selected sub-agent (multi-agent layout) |
| `memory/MEMORY.md` | Long-term memory |
| `memory/HISTORY.md` | Session history |
| `skills/*/SKILL.md` | Skill definition |
| `skills/*/_meta.json` | Skill metadata |
| `skills/*/scripts/*` | Skill scripts |
| `skills/*/setup.md` | Skill setup doc |
| `skills/*/operations.md` | Skill operations doc |
| `skills/*/boundaries.md` | Skill boundaries doc |

### openclaw

Root-per-agent: default agent at `~/.openclaw/workspace`, named agents at `~/.openclaw/workspace-<name>`.

| Pattern | Description |
|---------|-------------|
| `AGENTS.md` | Agent instructions |
| `SOUL.md` | Persona |
| `USER.md` | User profile |
| `TOOLS.md` | Tool definitions |
| `HEARTBEAT.md` | Scheduled tasks |
| `IDENTITY.md` | Agent identity card |
| `BOOTSTRAP.md` | First-run bootstrap |
| `MEMORY.md` | Long-term memory |
| `memory/*.md`, `memory/*.json` | Memory files |
| `skills/*/SKILL.md`, `skills/*/_meta.json`, `skills/*/scripts/*` | Skills |

### hermes

Single-agent install; root `~/.hermes`.

| Pattern | Description |
|---------|-------------|
| `SOUL.md` | Persona |
| `memories/*.md` | Memory files |
| `skills/*/SKILL.md`, `skills/*/DESCRIPTION.md`, `skills/*/_meta.json` | Skill definition + metadata |
| `skills/*/scripts/*`, `skills/*/references/*` | Skill scripts & references |
| `skills/*/*/...` | Nested skills (same set, one level deeper) |

### qwenpaw

Root-per-agent: `~/.qwenpaw/workspaces/<name>` (default agent = `workspaces/default`).

| Pattern | Description |
|---------|-------------|
| `AGENTS.md` | Agent instructions |
| `SOUL.md` | Persona |
| `PROFILE.md` | Identity + user profile |
| `BOOTSTRAP.md` | First-run bootstrap (auto-removed) |
| `MEMORY.md` | Long-term memory |
| `HEARTBEAT.md` | Scheduled tasks |
| `memory/*.md` | Daily memory files |
| `skills/*/SKILL.md`, `skills/*/_meta.json`, `skills/*/scripts/*` | Skills |

### openhuman

Workspace root: `~/.openhuman/workspace`.

| Pattern | Description |
|---------|-------------|
| `SOUL.md` | Persona |
| `IDENTITY.md` | Mission & values |
| `USER.md` | User profile |
| `PROFILE.md` | Onboarding-enriched profile |
| `MEMORY.md` | Long-term memory summary |
| `HEARTBEAT.md` | Periodic tasks |
| `wiki/*.md`, `wiki/summaries/*.md`, `wiki/notes/*.md` | Obsidian memory vault |
| `skills/*/SKILL.md`, `skills/*/_meta.json`, `skills/*/scripts/*` | Skills |

### qoder

File-per-agent + shared. Shared root `~/.qoder` (point `--local_dir` at a project's `.qoder/` to upload that instead). A sub-agent is one Markdown file `agents/<name>.md`; everything else is shared across sub-agents.

| Pattern | Description |
|---------|-------------|
| `AGENTS.md` | Shared agent instructions / memory |
| `agents/{name}.md` | Selected sub-agent definition |
| `commands/*.md` | Custom slash commands (shared) |
| `rules/*.md` | Rules (shared) |
| `skills/*/SKILL.md`, `skills/*/scripts/*`, `skills/*/references/*` | Skills (shared) |

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
| nanobot | SOUL.md, AGENTS.md, USER.md, TOOLS.md, HEARTBEAT.md, memory/MEMORY.md, memory/HISTORY.md |
| openclaw | SOUL.md, AGENTS.md, USER.md, TOOLS.md, HEARTBEAT.md, IDENTITY.md, BOOTSTRAP.md |
| hermes | SOUL.md, memories/USER.md |
| qwenpaw | SOUL.md, AGENTS.md, PROFILE.md, HEARTBEAT.md |
| openhuman | SOUL.md, IDENTITY.md, USER.md, HEARTBEAT.md |
| qoder | (no bundled defaults) |

### API

```
GET /harness/defaults/{product}
```

Returns `{success, product, files}` where `files` maps filenames to contents.
