---
slug: HarnessHub
title: Harness Hub
description: Personal workspace sync and share across Claw products
---

# Harness Hub (personal config sync)

HarnessHub syncs and shares personal workspaces across Claw products (nanobot, openclaw, hermes, …): memories, skills, and persona files in one place.

## Concepts

| Concept | Meaning |
|---------|---------|
| **user_id** | Stable user id |
| **agent_id** | Device or terminal id; one user can have many |
| **Claw** | Pair `(user_id, agent_id)`: one agent instance on one device |
| **Profile** | Server-side workspace snapshot (file contents + skill references) |
| **Allowlist** | Per-product glob list of files safe to sync (excludes `.env`, `auth.json`, …) |
| **Bundle** | JSON package of workspace files for transport |
| **Share token** | Short code or token others use to import your published agent setup |

## Sync model

- Sync is only between **the same `(user_id, agent_id)`** cloud profile and local disk
- **No automatic sync** across different devices
- Users manage multiple `agent_id` values in the Dashboard
- Synced content is workspace files (persona, memory, skills), **not** chat logs

```
Local workspace --sync up--> Ultron server --sync down--> local workspace
     |                        |
     |                        v
     |                  Share short code (6 chars)
     |                        |
     |              curl server/i/{code} | bash
     |                        |
     +------------------------+
```

## Supported products

| Product | Workspace root | Patterns |
|---------|------------------|----------|
| nanobot | `~/.nanobot/workspace/` | AGENTS.md, SOUL.md, USER.md, TOOLS.md, HEARTBEAT.md, memory/*.md, skills/*/* |
| openclaw | `~/.openclaw/workspace/` | Same as nanobot |
| hermes | `~/.hermes/` | config.yaml, SOUL.md, memories/*.md, skills/*/* |

All exclude: `.env`, `auth.json`, `sessions/`, `logs/`, hidden files.

## Share flow

1. User A runs sync up to upload the workspace
2. User A creates a share and gets a short code
3. User A sends the code to user B
4. User B runs one line:

```bash
curl -sL https://your-server/i/Ab3xK9 | bash
```

Share snapshots are **point-in-time**; later edits to the source profile do not change an existing token.

## Architecture

```
+-------------+     +-------------+     +-------------+
|   Nanobot   |     |  OpenClaw   |     |   Hermes    |
|  Allowlist  |     |  Allowlist  |     |  Allowlist  |
+------+------+     +------+------+     +------+------+
       |                   |                   |
       +-----------+-------+-------------------+
                   v
            HarnessBundle
                   |
                   v
          +----------------+
          | HarnessService |
          +--------+-------+
                   |
         +---------+---------+
         v         v         v
      agents    profiles   shares
   (SQLite)   (SQLite)   (SQLite)
```

## Terminal import

Server **`GET /i/{short_code}`** returns an install script; only `curl` and `bash` are required locally.

```bash
curl -fsSL https://your-server/i/<short_code>?product=nanobot | bash
```

Existing workspaces are backed up under `~/.ultron/harness-import-backups/` before overwrite; the script prints `rm` / `mkdir` / `cp` commands to restore.

Upload, download, and share creation are done via the **Dashboard** or authenticated HTTP (e.g. `POST /harness/sync/up`, `POST /harness/share`).

## Add a new product

1. Subclass `ClawWorkspaceAllowlist` in `ultron/services/harness/allowlist.py`
2. Set `product_name`, `workspace_root`, `patterns`
3. Register in `ALLOWLIST_REGISTRY`

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

## Per-product patterns

### nanobot

| Pattern | Role |
|---------|------|
| `AGENTS.md` | Agent instructions |
| `SOUL.md` | Persona |
| `USER.md` | User profile |
| `TOOLS.md` | Tool definitions |
| `HEARTBEAT.md` | Scheduled tasks |
| `memory/MEMORY.md` | Long-term memory |
| `memory/HISTORY.md` | Session history |
| `skills/*/SKILL.md` | Skill body |
| `skills/*/_meta.json` | Skill metadata |
| `skills/*/scripts/*` | Skill scripts |
| `skills/*/setup.md` | Skill setup |
| `skills/*/operations.md` | Skill operations |
| `skills/*/boundaries.md` | Skill boundaries |

### openclaw

Same layout as nanobot.

### hermes

| Pattern | Role |
|---------|------|
| `config.yaml` | Agent config |
| `SOUL.md` | Persona |
| `memories/*.md` | Memory files |
| `skills/*/SKILL.md` | Skill body |
| `skills/*/_meta.json` | Metadata |
| `skills/*/scripts/*` | Scripts |

## Bundle schema

JSON stored in `harness_profiles.resources_json` and `harness_shares.snapshot_json`:

```json
{
    "product": "nanobot",
    "resources": {
        "SOUL.md": "file contents...",
        "memory/MEMORY.md": "file contents..."
    },
    "collected_at": "2026-04-06T12:00:00+00:00"
}
```

## Limitations

- Text only (no binary sync)
- Max 1 MB per file
- Share snapshots are static copies
- No merge semantics: last sync up wins

API details: [HTTP API](../API/HttpAPI.md) and [Python SDK](../API/SDK.md) HarnessHub sections.
