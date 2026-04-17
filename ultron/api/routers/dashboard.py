# Copyright (c) ModelScope Contributors. All rights reserved.
import io
import json as _json
import os
import zipfile

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response

from ultron import server_state
from ultron.api.paths import (
    AGENT_SKILL_PACKAGE_DIR,
    DASHBOARD_DIR,
    DASHBOARD_DIST,
    SKILLS_ROOT,
)

router = APIRouter(tags=["dashboard"])


def mount_dashboard_assets(app) -> None:
    from fastapi.staticfiles import StaticFiles

    assets_dir = os.path.join(DASHBOARD_DIST, "assets")
    if os.path.isdir(assets_dir):
        app.mount(
            "/assets",
            StaticFiles(directory=assets_dir),
            name="dashboard-assets",
        )

    # Favicon and other files from vite dist root (prod) or dashboard/public (dev).
    # Root URLs like /modelscope.svg are not served unless mounted here.
    if os.path.isfile(os.path.join(DASHBOARD_DIST, "index.html")):
        static_root = DASHBOARD_DIST
    else:
        static_root = os.path.join(DASHBOARD_DIR, "public")
    if os.path.isdir(static_root):
        app.mount(
            "/dashboard-static",
            StaticFiles(directory=static_root, html=False),
            name="dashboard-static",
        )

    repo_asset_dir = os.path.normpath(
        os.path.join(os.path.dirname(DASHBOARD_DIST), "..", "asset")
    )
    if os.path.isdir(repo_asset_dir):
        app.mount(
            "/asset",
            StaticFiles(directory=repo_asset_dir),
            name="repo-assets",
        )


@router.get("/dashboard")
async def dashboard_page():
    dist_html = os.path.join(DASHBOARD_DIST, "index.html")
    if os.path.isfile(dist_html):
        return FileResponse(
            dist_html,
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    html = os.path.join(DASHBOARD_DIR, "index.html")
    if not os.path.isfile(html):
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return FileResponse(
        html,
        media_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/skills")
@router.get("/leaderboard")
@router.get("/quickstart")
@router.get("/harness")
async def dashboard_spa_routes():
    dist_html = os.path.join(DASHBOARD_DIST, "index.html")
    if os.path.isfile(dist_html):
        return FileResponse(
            dist_html,
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    html = os.path.join(DASHBOARD_DIR, "index.html")
    if not os.path.isfile(html):
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return FileResponse(
        html,
        media_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/dashboard/overview")
async def dashboard_overview():
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    mem_stats = u.get_memory_stats()
    internal_count = (
        u.db.count_skills(status="active")
        if hasattr(u.db, "count_skills")
        else 0
    )
    try:
        with u.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM skills WHERE status = 'active'")
            internal_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM catalog_skills")
            catalog_count = cursor.fetchone()[0]
            cursor.execute(
                "SELECT categories, COUNT(*) as cnt FROM skills WHERE status = 'active' GROUP BY categories"
            )
            skill_cats: dict = {}
            for r in cursor.fetchall():
                try:
                    cats = _json.loads(r["categories"]) if r["categories"] else []
                except Exception:
                    cats = []
                for c in cats:
                    skill_cats[c] = skill_cats.get(c, 0) + r["cnt"]
            cursor.execute(
                "SELECT category_name, COUNT(*) as cnt FROM catalog_skills GROUP BY category_name ORDER BY cnt DESC"
            )
            catalog_cats = {
                r["category_name"]: r["cnt"]
                for r in cursor.fetchall()
                if r["category_name"]
            }
    except Exception:
        catalog_count = 0
        skill_cats = {}
        catalog_cats = {}

    return {
        "memory": mem_stats,
        "skills": {
            "internal": internal_count,
            "catalog": catalog_count,
            "internal_categories": skill_cats,
            "catalog_categories": catalog_cats,
        },
    }


@router.get("/dashboard/agent-skill-package")
async def download_agent_skill_package():
    if not os.path.isdir(AGENT_SKILL_PACKAGE_DIR):
        raise HTTPException(
            status_code=404,
            detail="Skill package ultron-1.0.0 not found on server",
        )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(AGENT_SKILL_PACKAGE_DIR):
            for fn in files:
                fp = os.path.join(root, fn)
                arcname = os.path.relpath(fp, SKILLS_ROOT)
                zf.write(fp, arcname)
    body = buf.getvalue()
    return Response(
        content=body,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="ultron-1.0.0.zip"',
            "Content-Length": str(len(body)),
        },
    )


@router.get("/dashboard/memories")
async def dashboard_memories(
    q: str = Query("", description="Keyword search"),
    memory_type: str = Query("", description="Filter by type"),
    tier: str = Query("", description="Filter by tier"),
    sort: str = Query("hit_count", description="Sort: hit_count or created_at"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    offset = (page - 1) * page_size
    rows, total = u.db.search_memories_by_text(
        q=q,
        memory_type=memory_type,
        tier=tier,
        sort=sort,
        limit=page_size,
        offset=offset,
    )
    return {"data": rows, "total": total, "page": page, "page_size": page_size}


@router.get("/dashboard/skills")
async def dashboard_skills(
    q: str = Query("", description="Keyword search"),
    source: str = Query("", description="internal or catalog"),
    category: str = Query("", description="Filter by category"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    offset = (page - 1) * page_size
    rows, total = u.db.search_skills_by_text(
        q=q,
        source=source,
        category=category,
        limit=page_size,
        offset=offset,
    )
    return {"data": rows, "total": total, "page": page, "page_size": page_size}


@router.get("/dashboard/skills/internal/{slug}/skill-md")
async def dashboard_internal_skill_md(slug: str):
    """Return raw SKILL.md text for an internal (Ultron-published) skill."""
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    text = u.get_internal_skill_md_text(slug)
    if text is None:
        raise HTTPException(
            status_code=404,
            detail="Skill not found or SKILL.md missing on server",
        )
    return {"slug": slug, "content": text}


@router.get("/dashboard/leaderboard")
async def dashboard_leaderboard(
    limit: int = Query(50, ge=1, le=200),
):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    return u.db.get_memory_leaderboard(limit=limit)
