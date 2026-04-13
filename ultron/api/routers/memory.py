# Copyright (c) ModelScope Contributors. All rights reserved.
from fastapi import APIRouter

from ultron import server_state
from ultron.api.schemas import (
    IngestRequest,
    IngestTextRequest,
    MemoryDetailsRequest,
    SearchMemoryRequest,
    UploadMemoryRequest,
)

router = APIRouter(tags=["memory"])


@router.post("/memory/upload")
async def upload_memory(request: UploadMemoryRequest):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    record = u.upload_memory(
        content=request.content,
        context=request.context,
        resolution=request.resolution,
        tags=request.tags,
    )
    return {
        "success": True,
        "data": {
            "id": record.id,
            "memory_type": record.memory_type,
            "tier": record.tier,
            "hit_count": record.hit_count,
            "status": record.status,
        },
    }


@router.post("/memory/search")
async def search_memory(request: SearchMemoryRequest):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    results = u.search_memories(
        query=request.query,
        tier=request.tier,
        limit=request.limit,
        detail_level=request.detail_level,
    )
    return {
        "success": True,
        "count": len(results),
        "data": [r.to_dict(include_embedding=False) for r in results],
    }


@router.post("/memory/details")
async def get_memory_details(request: MemoryDetailsRequest):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    records = u.get_memory_details(request.memory_ids)
    return {
        "success": True,
        "count": len(records),
        "data": [r.to_dict(include_embedding=False) for r in records],
    }


@router.get("/memory/stats")
async def get_memory_stats():
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    return {"success": True, "data": u.get_memory_stats()}


@router.post("/ingest")
async def ingest(request: IngestRequest):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    result = u.ingest(
        paths=request.paths,
        agent_id=request.agent_id,
    )
    return {"success": result.get("successful", 0) > 0, "data": result}


@router.post("/ingest/text")
async def ingest_text(request: IngestTextRequest):
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    result = u.ingest_text(
        text=request.text,
    )
    return {"success": result.get("success", False), "data": result}
