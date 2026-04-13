# Copyright (c) ModelScope Contributors. All rights reserved.
from fastapi import APIRouter

from ultron import server_state
from ultron.api.schemas import (
    InstallSkillRequest,
    SearchSkillsRequest,
    UploadSkillsRequest,
)

router = APIRouter(tags=["skills"])


@router.post("/skills/search")
async def search_skills(request: SearchSkillsRequest):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    results = u.search_skills(
        query=request.query,
        limit=request.limit,
    )
    return {
        "success": True,
        "count": len(results),
        "data": [
            {
                "slug": r.skill.meta.slug,
                "version": r.skill.meta.version,
                "name": r.skill.name,
                "description": r.skill.description,
                "categories": r.skill.categories,
                "similarity_score": round(r.similarity_score, 4),
                "combined_score": round(r.combined_score, 4),
            }
            for r in results
        ],
    }


@router.get("/skills")
async def list_skills():
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    skills = u.list_all_skills()
    return {"success": True, "count": len(skills), "data": skills}


@router.post("/skills/upload")
async def upload_skills(request: UploadSkillsRequest):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    result = u.upload_skills(
        paths=request.paths,
    )
    return {"success": result.get("successful", 0) > 0, "data": result}


@router.post("/skills/install")
async def install_skill(request: InstallSkillRequest):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    result = u.install_skill_to(
        full_name=request.full_name,
        target_dir=request.target_dir,
    )
    return result
