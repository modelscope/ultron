# Copyright (c) ModelScope Contributors. All rights reserved.
import json as _json
import re as _re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from ultron import server_state
from ultron.api.deps import get_current_user
from ultron.api.schemas import (
    CreateShareRequest,
    DeleteAgentRequest,
    DeleteShareRequest,
    SyncDownRequest,
    SyncUpRequest,
)
from ultron.services.harness.defaults import get_defaults
from ultron.services.harness.merge import merge_resources

router = APIRouter(tags=["harness"])


def _build_export_script(share: dict, product: str = "") -> PlainTextResponse:
    snapshot = share["snapshot"]
    if isinstance(snapshot, str):
        snapshot = _json.loads(snapshot)
    source_product = snapshot.get("product", "nanobot")
    resolved_product = product or source_product
    resources = dict(snapshot.get("resources", {}))
    ms_import_key = "skills/.ultron_modelscope_imports.json"
    ms_raw = resources.pop(ms_import_key, "")
    ms_imports: list[str] = []
    if ms_raw:
        try:
            parsed = _json.loads(ms_raw)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        full_name = str(item.get("full_name", "")).strip()
                        if full_name:
                            ms_imports.append(full_name)
        except Exception:
            pass

    if resolved_product != source_product:
        source_defaults = get_defaults(source_product)
        target_defaults = get_defaults(resolved_product)
        result = merge_resources(
            incoming=resources,
            source_product=source_product,
            target_product=resolved_product,
            source_defaults=source_defaults,
            target_defaults=target_defaults,
        )
        resources = result.merged_files

    WORKSPACE_PATHS = {
        "nanobot": "$HOME/.nanobot/workspace",
        "openclaw": "$HOME/.openclaw/workspace",
        "hermes": "$HOME/.hermes",
    }
    ws_path = WORKSPACE_PATHS.get(resolved_product, WORKSPACE_PATHS["nanobot"])

    short_code = share.get("short_code", "")
    token = share.get("token", "")
    label = short_code or token[:8]

    # Bash-safe product label for paths and messages (snapshot product is validated upstream).
    safe_product = _re.sub(r"[^a-zA-Z0-9._-]", "_", resolved_product) or "nanobot"

    lines = [
        "#!/usr/bin/env bash",
        "# Ultron HarnessHub — Workspace Bundle",
        f"# Product: {resolved_product}",
        f"# Files: {len(resources)}",
        f"# Source: {share.get('source_user_id', '?')} / {share.get('source_agent_id', '?')}",
        f"# Code: {label}",
        "",
        "set -e",
        "",
        f'WORKSPACE="{ws_path}"',
        'BACKUP_DIR=""',
        'BACKUP_ROOT="$HOME/.ultron/harness-import-backups"',
        "",
        'echo "==> Ultron HarnessHub Bundle Installer"',
        f'echo "    Product:   {resolved_product}"',
        f'echo "    Files:     {len(resources)}"',
        f'echo "    Target:    {ws_path}"',
        'echo ""',
        "",
        'echo "WARNING: This import overwrites files in your local agent workspace."',
        f'echo "         Target: $WORKSPACE  ({resolved_product})"',
        'echo "         If the workspace already has files, a full copy is saved under ~/.ultron/harness-import-backups/"',
        'echo "         before any changes. After import, the script prints shell commands to restore from that backup."',
        'echo ""',
        'if [ -t 0 ]; then',
        '  read -r -p "Continue with import? [y/N] " ULTRON_IMPORT_REPLY',
        '  case "$ULTRON_IMPORT_REPLY" in y|Y|yes|YES) ;; *) echo "Aborted."; exit 1;; esac',
        "else",
        '  echo "(non-interactive: continuing; backup will still run if the workspace is non-empty)"',
        "fi",
        'echo ""',
        "",
        'if [ -d "$WORKSPACE" ] && [ -n "$(ls -A "$WORKSPACE" 2>/dev/null)" ]; then',
        '  STAMP=$(date +%Y%m%d-%H%M%S)',
        f'  BACKUP_DIR="$BACKUP_ROOT/{safe_product}-{label}-$STAMP"',
        '  mkdir -p "$BACKUP_DIR"',
        '  cp -a "$WORKSPACE"/. "$BACKUP_DIR"/',
        '  echo "==> Previous workspace backed up to: $BACKUP_DIR"',
        "else",
        '  echo "==> No existing workspace to back up (empty or missing)."',
        "fi",
        'echo ""',
        "",
        'mkdir -p "$WORKSPACE"',
        'mkdir -p "$WORKSPACE/skills"',
        "",
    ]

    if ms_imports:
        lines.extend(
            [
                'echo "==> Installing ModelScope skills declared by this bundle"',
                'if ! command -v modelscope >/dev/null 2>&1; then',
                '  echo "modelscope CLI not found. Please install modelscope first."',
                '  exit 1',
                'fi',
                "",
            ]
        )
        for full_name in ms_imports:
            skill_name = full_name.rsplit("/", 1)[-1] if "/" in full_name else full_name
            skill_name = skill_name.lstrip("@")
            safe_skill_name = _re.sub(r"[^a-zA-Z0-9._-]", "_", skill_name) or "skill"
            safe_full_name = full_name.replace('"', '\\"')
            lines.extend(
                [
                    f'echo "-> modelscope skills add {safe_full_name}"',
                    f'modelscope skills add "{safe_full_name}"',
                    f'if [ ! -d "$HOME/.agents/skills/{safe_skill_name}" ]; then',
                    f'  echo "Installed skill not found: $HOME/.agents/skills/{safe_skill_name}"',
                    "  exit 1",
                    "fi",
                    f'rm -rf "$WORKSPACE/skills/{safe_skill_name}"',
                    f'cp -R "$HOME/.agents/skills/{safe_skill_name}" "$WORKSPACE/skills/{safe_skill_name}"',
                    "",
                ]
            )

    for i, (rel_path, content) in enumerate(resources.items(), 1):
        safe_path = rel_path.replace('"', '\\"')
        delim = f"__ULTRON_EOF_{i}__"
        lines.append(f'echo "[{i}/{len(resources)}] Writing {safe_path}"')
        lines.append(f'mkdir -p "$WORKSPACE/$(dirname "{safe_path}")"')
        lines.append(f"cat > \"$WORKSPACE/{safe_path}\" << '{delim}'")
        lines.append(content)
        lines.append(delim)
        lines.append("")

    lines.extend(
        [
            'echo ""',
            f'echo "==> Done! {len(resources)} files written to {ws_path}"',
            f'echo "    Your {resolved_product} workspace is ready."',
        ]
    )
    lines.extend(
        [
            'if [ -n "$BACKUP_DIR" ]; then',
            '  echo ""',
            '  echo "==> RESTORE previous workspace (if needed), run:"',
            '  echo "    rm -rf \\\"$WORKSPACE\\\" && mkdir -p \\\"$WORKSPACE\\\" && cp -a \\\"$BACKUP_DIR\\\"/. \\\"$WORKSPACE\\\"/"',
            "fi",
        ]
    )

    script = "\n".join(lines) + "\n"
    filename = f"ultron-bundle-{resolved_product}-{label}.sh"
    return PlainTextResponse(
        content=script,
        media_type="text/x-shellscript",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/harness/agents")
async def list_agents(user: dict = Depends(get_current_user)):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    agents = u.list_agents(user["username"])
    return {"success": True, "count": len(agents), "data": agents}


@router.delete("/harness/agents")
async def delete_agent(
    request: DeleteAgentRequest, user: dict = Depends(get_current_user)
):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    ok = u.remove_agent(user_id=user["username"], agent_id=request.agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"success": True}


@router.post("/harness/sync/up")
async def harness_sync_up(
    request: SyncUpRequest, user: dict = Depends(get_current_user)
):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    data = u.harness_sync_up(
        user_id=user["username"],
        agent_id=request.agent_id,
        product=request.product,
        resources=request.resources,
    )
    return {"success": True, "data": data}


@router.post("/harness/sync/down")
async def harness_sync_down(
    request: SyncDownRequest, user: dict = Depends(get_current_user)
):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    data = u.harness_sync_down(user_id=user["username"], agent_id=request.agent_id)
    if not data:
        raise HTTPException(
            status_code=404, detail="No profile found for this user/agent"
        )
    return {"success": True, "data": data}


@router.get("/harness/profile")
async def get_harness_profile(
    agent_id: str = Query(..., description="Device identifier"),
    user: dict = Depends(get_current_user),
):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    data = u.get_harness_profile(user_id=user["username"], agent_id=agent_id)
    if not data:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"success": True, "data": data}


@router.get("/harness/profiles")
async def list_harness_profiles(user: dict = Depends(get_current_user)):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    data = u.get_profiles_by_user(user_id=user["username"])
    return {"success": True, "data": data}


@router.post("/harness/share")
async def create_harness_share(
    request: CreateShareRequest, user: dict = Depends(get_current_user)
):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    try:
        data = u.create_harness_share(
            user_id=user["username"],
            agent_id=request.agent_id,
            visibility=request.visibility,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "data": data}


@router.get("/harness/shares")
async def list_harness_shares(user: dict = Depends(get_current_user)):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    shares = u.list_harness_shares(user["username"])
    return {"success": True, "count": len(shares), "data": shares}


@router.delete("/harness/share")
async def delete_harness_share(
    request: DeleteShareRequest, _user: dict = Depends(get_current_user),
):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    ok = u.delete_harness_share(token=request.token)
    if not ok:
        raise HTTPException(status_code=404, detail="Share token not found")
    return {"success": True}


@router.get("/harness/share/export/{token}")
async def export_harness_bundle(
    token: str,
    product: str = Query("", description="Override product: nanobot/openclaw/hermes"),
):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    share = u.db.get_share(token)
    if not share:
        raise HTTPException(status_code=404, detail="Share token not found")
    return _build_export_script(share, product)


@router.get("/i/{code}")
async def export_by_short_code(
    code: str,
    product: str = Query("", description="Override product: nanobot/openclaw/hermes"),
):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    share = u.db.get_share_by_code(code)
    if not share:
        raise HTTPException(status_code=404, detail="Short code not found")
    return _build_export_script(share, product)


@router.get("/harness/defaults/{product}")
async def get_harness_defaults(product: str):
    defaults = get_defaults(product)
    return {"success": True, "product": product, "files": defaults}


@router.get("/harness/soul-presets")
async def list_soul_presets():
    svc = server_state.soul_preset_service
    if svc is None:
        raise RuntimeError("Server not initialized")
    categories = svc.list_presets()
    return {"success": True, "data": {"categories": categories}}


@router.get("/harness/soul-presets/{preset_id}")
async def get_soul_preset(preset_id: str):
    svc = server_state.soul_preset_service
    if svc is None:
        raise RuntimeError("Server not initialized")
    entry = svc.get_preset(preset_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Preset not found")
    return {
        "success": True,
        "data": {
            "id": entry["id"],
            "name": entry["name"],
            "description": entry.get("description", ""),
            "emoji": entry.get("emoji", ""),
            "category": entry["category"],
            "body": entry["body"],
        },
    }


@router.post("/harness/soul-presets/build")
async def build_role_resources(
    request: dict,
    _user: dict = Depends(get_current_user),
):
    svc = server_state.soul_preset_service
    if svc is None:
        raise RuntimeError("Server not initialized")
    preset_ids = request.get("preset_ids", [])
    if not preset_ids or not isinstance(preset_ids, list):
        raise HTTPException(status_code=400, detail="preset_ids must be a non-empty list")
    resources = svc.build_role_resources(preset_ids)
    return {"success": True, "data": {"resources": resources}}


@router.get("/harness/showcase")
async def list_showcases(lang: str = Query("zh", description="Language: zh or en")):
    svc = server_state.showcase_service
    if svc is None:
        raise RuntimeError("Server not initialized")
    return {"success": True, "data": svc.list_showcases(lang)}


@router.get("/harness/showcase/{slug}")
async def get_showcase(
    slug: str,
    lang: str = Query("zh", description="Language: zh or en"),
):
    svc = server_state.showcase_service
    if svc is None:
        raise RuntimeError("Server not initialized")
    entry = svc.get_showcase(slug, lang)
    if not entry:
        raise HTTPException(status_code=404, detail="Showcase not found")
    return {"success": True, "data": entry}
