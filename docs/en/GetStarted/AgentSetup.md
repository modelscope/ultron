---
slug: AgentSetup
title: Agent setup
description: Connect an AI assistant to Ultron
---

# Agent setup

Install the Ultron skill pack into your assistant workspace so the assistant gains group memory and skill search.

## Quick start

A deployed Ultron instance provides a guided quickstart page:

**[Quickstart Guide](https://writtingforfun-ultron.ms.show/quickstart)** — follow the steps in the browser.

## Manual setup

### 1. Copy the skill pack

Copy `skills/ultron-1.0.0/` from the repo root into your assistant workspace `skills/` directory:

```bash
# Example: Nanobot
cp -r skills/ultron-1.0.0 ~/.nanobot/workspace/skills/
```

### 2. Set the Ultron API base URL

```bash
export ULTRON_API_URL=https://writtingforfun-ultron.ms.show
```

### 3. Let the assistant run setup

Send the assistant:

```
Set up Ultron using setup.md
```

The assistant reads `skills/ultron-1.0.0/setup.md` and typically:

- Creates `ULTRON_AGENT_ID` (UUID for ingest progress isolation)
- Updates `SOUL.md` (Ultron retrieval hints)
- Configures periodic session ingest

### 4. Verify

```bash
cd ~/.nanobot/workspace
python3 skills/ultron-1.0.0/scripts/ultron_client.py '{"action":"get_stats"}'
```

Expect `"status": "ok"` in the response.

## Skill pack layout

```
skills/ultron-1.0.0/
├── SKILL.md           # Main entry (actions, call order)
├── setup.md           # Install guide (read by the assistant)
├── operations.md      # Memory ops and upload templates
├── boundaries.md      # Safety boundaries
└── scripts/
    ├── ultron_client.py   # API client
    └── memory_sync.py     # Memory sync helper
```

## No self-hosted server?

If you use a public Ultron endpoint, the steps above are enough; you do not need the Ultron source tree. To run your own server, see [Server deployment](Installation.md).
