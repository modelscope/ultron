# Copyright (c) ModelScope Contributors. All rights reserved.
from fastapi import APIRouter

from ultron import server_state
from ultron.api.schemas import (
    EvolveSkillRequest,
    InstallSkillRequest,
    SearchSkillsRequest,
    SkillFeedbackRequest,
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


@router.post("/skills/evolve")
async def evolve_skills(request: EvolveSkillRequest):
    """Manually trigger skill evolution (crystallization + re-crystallization)."""
    evolution_engine = server_state.evolution_engine
    if evolution_engine is None:
        return {"success": False, "error": "Evolution engine not initialized"}

    if request.cluster_id:
        from ultron.core.models import KnowledgeCluster
        cluster_dict = evolution_engine.db.get_cluster(request.cluster_id)
        if not cluster_dict:
            return {"success": False, "error": f"Cluster {request.cluster_id} not found"}
        cluster = KnowledgeCluster.from_dict(cluster_dict)
        if cluster.skill_slug:
            result = evolution_engine.recrystallize_skill(cluster, trigger="manual")
        else:
            result = evolution_engine.crystallize_cluster(cluster, trigger="manual")
        return {
            "success": result is not None,
            "data": {"skill_slug": result.meta.slug, "version": result.meta.version} if result else None,
        }

    summary = evolution_engine.run_evolution_cycle(limit=request.limit)
    return {"success": True, "data": summary}


@router.get("/skills/clusters")
async def list_clusters():
    """List all knowledge clusters and their status."""
    cluster_service = server_state.cluster_service
    if cluster_service is None:
        return {"success": False, "error": "Cluster service not initialized"}

    clusters = cluster_service.db.get_all_clusters()
    ready_crystallize = [c.cluster_id for c in cluster_service.get_clusters_ready_to_crystallize()]
    ready_recrystallize = [c.cluster_id for c in cluster_service.get_clusters_ready_to_recrystallize()]

    data = []
    for c in clusters:
        cid = c["cluster_id"]
        data.append({
            "cluster_id": cid,
            "topic": c.get("topic", ""),
            "size": len(c.get("memory_ids", [])),
            "skill_slug": c.get("skill_slug"),
            "superseded_slugs": c.get("superseded_slugs", []),
            "ready_to_crystallize": cid in ready_crystallize,
            "ready_to_recrystallize": cid in ready_recrystallize,
            "created_at": c.get("created_at"),
            "last_updated_at": c.get("last_updated_at"),
        })

    return {"success": True, "count": len(data), "data": data}


@router.get("/skills/evolution-history")
async def evolution_history(skill_slug: str = "", limit: int = 20):
    """Get evolution history for a skill or all skills."""
    evolution_engine = server_state.evolution_engine
    if evolution_engine is None:
        return {"success": False, "error": "Evolution engine not initialized"}

    if skill_slug:
        records = evolution_engine.db.get_evolution_history(skill_slug, limit)
    else:
        records = []
        for cluster in evolution_engine.db.get_all_clusters():
            if cluster.get("skill_slug"):
                records.extend(evolution_engine.db.get_evolution_history(cluster["skill_slug"], 5))
        records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        records = records[:limit]

    return {"success": True, "count": len(records), "data": records}


@router.post("/skills/feedback")
async def skill_feedback(request: SkillFeedbackRequest):
    """Optional: agent reports skill usage result, converted to memory for evolution."""
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")

    if request.feedback:
        u.upload_memory(
            content=f"Skill '{request.skill_slug}' feedback: {request.feedback}",
            context=f"Agent {request.agent_id} used skill '{request.skill_slug}', success={request.success}",
            resolution=request.feedback if not request.success else "",
            tags=["skill-feedback", request.skill_slug],
        )

    return {"success": True}
