# Copyright (c) ModelScope Contributors. All rights reserved.
from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from ultron import server_state

router = APIRouter(tags=["system"])


@router.get("/")
async def root():
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "ultron",
        "version": "1.0.0",
        "architecture": "collective-intelligence",
    }


@router.get("/stats")
async def get_stats():
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    return u.get_stats()
