# Setup Guide

## 1. Generate Agent ID

Each agent requires a unique identifier for ingest progress isolation. Append it to your env file once (skipped if the key already exists):

```bash
export ULTRON_AGENT_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
echo "ULTRON_AGENT_ID=$ULTRON_AGENT_ID" >> ~/.bashrc
source ~/.bashrc
```

## 2. Verify Connection

```bash
python3 skills/ultron-1.0.0/scripts/ultron_client.py '{"action": "get_stats"}'
```

Expected response contains `"status": "ok"`.

## 3. Configure SOUL.md

Add the Ultron bootstrap block to `SOUL.md`:

```markdown
## Ultron — Collective Memory & Skill System

For every task-oriented user message, perform remote retrieval first (if the service is available):
1. `search_memory`: Retrieve collective experience
2. `search_skills`: Retrieve available skills
When reusable experience is encountered, upload it via `upload_memory` or `ingest_text`.
Preferences → local only; objective experience → upload to Ultron.
```

## 4. Schedule automatic memory sync

In-session experience must be **synced on a schedule** (for example once per day). Create a **timer or cron job** (or your agent platform's built-in scheduler) that runs the ingest command below.

### Command the job must run

Invoke `ultron_client.py` with `ingest` so the server incrementally extracts memories (progress is keyed by `agent_id` + file path):

```bash
python3 skills/ultron-1.0.0/scripts/ultron_client.py '{"action":"ingest","paths":["<sessions-dir>"],"agent_id":"<ULTRON_AGENT_ID>"}'
```

Where:
- `<sessions-dir>` should be replaced with the actual sessions directory path (e.g., `~/.nanobot/workspace/sessions`)
- `<ULTRON_AGENT_ID>` should be replaced with the UUID generated in step 1

## 5. Configure AGENTS.md

Add the following block to `AGENTS.md` (or the agent's main instruction file) so the agent proactively queries Ultron on every task:

```markdown
## Ultron — Collective Memory & Skill System

You have access to a shared remote memory and skill system called Ultron. You MUST use it proactively.

### Before Every Task (MANDATORY — DO NOT SKIP)

For every user request that requires reasoning or action (skip only for pure greetings):

1. **Search memory first**:
   ```bash
   python3 skills/ultron-1.0.0/scripts/ultron_client.py '{"action":"search_memory","query":"<user intent in 10-30 words>","detail_level":"l1","limit":5}'
   ```
2. If relevant memories are found, fetch full text before acting:
   ```bash
   python3 skills/ultron-1.0.0/scripts/ultron_client.py '{"action":"get_memory_details","memory_ids":["<id1>","<id2>"]}'
   ```
3. **Search skills when needed** (unfamiliar domain, need a tool/workflow/methodology):
   ```bash
   python3 skills/ultron-1.0.0/scripts/ultron_client.py '{"action":"search_skills","query":"<user intent>","limit":3}'
   ```

### After Task Completion (Upload Valuable Experience)

When you encounter reusable, objective knowledge (error fixes, technical patterns, life tips):
```bash
python3 skills/ultron-1.0.0/scripts/ultron_client.py '{"action":"upload_memory","content":"<description>","context":"<environment>","resolution":"<solution>","tags":["tag1","tag2"]}'
```

When the user corrects you and the correction is objective (not a personal preference):
```bash
python3 skills/ultron-1.0.0/scripts/ultron_client.py '{"action":"ingest_text","text":"<correction details>"}'
```

**Subjective stays local, objective goes remote.** Personal preferences (format, style, tone) are never uploaded. See `skills/ultron-1.0.0/boundaries.md` for the full safety boundary rules.

### SELF-CHECK (MANDATORY)
- [ ] Did I search Ultron memory before starting this task?
- [ ] Did I fetch full details for any relevant hits?
- [ ] After completing the task, is there reusable experience worth uploading?
```
