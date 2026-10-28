# Copyright (c) ModelScope Contributors. All rights reserved.
"""Repository management API (ModelScope-hub style).

Implements the contract from the "Agent 仓库管理接口设计文档": a hub-style
``/api/v1/agents/*`` surface for getting and uploading the harness information
ultron already stores. It is a thin adapter over the existing harness storage:

    :Path (user/org)  <->  user_id (the authenticated caller)
    :Name             <->  agent_id
    Framework         <->  product
    repo files        <->  harness_profiles.resources_json {rel_path: content}

Binary/LFS files are not yet supported by the underlying text-only store; LFS
``type: "lfs"`` actions are rejected with a clear error (see commit_repo).
"""

import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException, Query

from ultron import server_state
from ultron.api.deps import get_current_user
from ultron.api.schemas import (
    CommitRequest,
    CreateRepoRequest,
    LfsBatchRequest,
)
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1", tags=["repo"])


def _ultron():
    u = server_state.ultron
    if u is None:
        raise RuntimeError("Server not initialized")
    return u


def _ensure_owner(path: str, user: dict):
    """The repo Path must match the authenticated user (no org support yet)."""
    if path != user["username"]:
        raise HTTPException(
            status_code=403,
            detail=f"Path '{path}' does not match the authenticated user",
        )


def _get_profile_or_404(u, user_id: str, name: str) -> dict:
    profile = u.get_harness_profile(user_id=user_id, agent_id=name)
    if not profile:
        raise HTTPException(status_code=404, detail="Repository not found")
    return profile


# ---- 1. Check repository exists ----


@router.get("/agents/{path}/{name}")
async def check_repo(path: str, name: str, user: dict = Depends(get_current_user)):
    _ensure_owner(path, user)
    u = _ultron()
    profile = _get_profile_or_404(u, path, name)
    return {
        "success": True,
        "data": {
            "Path": path,
            "Name": name,
            "Framework": profile.get("product", ""),
            "Revision": profile.get("revision"),
            "UpdatedAt": profile.get("updated_at"),
        },
    }


# ---- 2. Create repository ----


@router.post("/agents")
async def create_repo(
    request: CreateRepoRequest, user: dict = Depends(get_current_user)
):
    _ensure_owner(request.Path, user)
    u = _ultron()
    existing = u.get_harness_profile(user_id=request.Path, agent_id=request.Name)
    if existing:
        raise HTTPException(status_code=409, detail="Repository already exists")
    # Initialize an empty profile carrying the framework/product.
    product = request.Framework or "nanobot"
    data = u.harness_sync_up(
        user_id=request.Path,
        agent_id=request.Name,
        product=product,
        resources={},
    )
    return {
        "success": True,
        "data": {
            "Path": request.Path,
            "Name": request.Name,
            "Framework": product,
            "Revision": data.get("revision"),
        },
    }


# ---- 3.1 Get LFS upload address ----


@router.post("/repos/agents/{path}/{name}/info/lfs/objects/batch")
async def lfs_batch(
    path: str,
    name: str,
    request: LfsBatchRequest,
    user: dict = Depends(get_current_user),
):
    _ensure_owner(path, user)
    # Binary/LFS storage is not yet supported by the text-only harness store.
    raise HTTPException(
        status_code=501,
        detail=(
            "LFS (binary) uploads are not supported yet. Commit text files with "
            "type='normal' and base64 content via /commit/master instead."
        ),
    )


# ---- 3.2 Commit files ----


@router.post("/repos/agents/{path}/{name}/commit/{revision}")
async def commit_repo(
    path: str,
    name: str,
    revision: str,
    request: CommitRequest,
    user: dict = Depends(get_current_user),
):
    _ensure_owner(path, user)
    u = _ultron()
    profile = _get_profile_or_404(u, path, name)
    resources = dict(profile.get("resources", {}))
    product = profile.get("product", "nanobot")

    for action in request.actions:
        if action.action == "delete":
            resources.pop(action.path, None)
            continue
        if action.action not in ("create", "update"):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported action '{action.action}' for {action.path}",
            )
        if action.type == "lfs":
            raise HTTPException(
                status_code=501,
                detail=f"LFS (binary) file '{action.path}' is not supported yet",
            )
        # normal text file: base64-decode into UTF-8 text
        try:
            raw = base64.b64decode(action.content, validate=True)
            text = raw.decode("utf-8")
        except (binascii.Error, ValueError):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid base64 content for '{action.path}'",
            )
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=400,
                detail=f"File '{action.path}' is not valid UTF-8 text (binary needs LFS)",
            )
        resources[action.path] = text

    data = u.harness_sync_up(
        user_id=path, agent_id=name, product=product, resources=resources
    )
    return {
        "success": True,
        "data": {
            "commit_message": request.commit_message,
            "Revision": data.get("revision"),
            "files": len(resources),
        },
    }


# ---- 4.1 List repository files ----


class DeleteFileRequest(BaseModel):
    branch: str = Field("master", description="Branch name")
    file_path: str = Field(..., description="File path to delete")
    commit_message: str = Field("", description="Commit message")


@router.delete("/agents/{path}/{name}/repo/file")
async def delete_repo_file(
    path: str,
    name: str,
    request: DeleteFileRequest,
    user: dict = Depends(get_current_user),
):
    """Delete a single file from the repo."""
    _ensure_owner(path, user)
    u = _ultron()
    profile = _get_profile_or_404(u, path, name)
    resources = dict(profile.get("resources", {}))
    product = profile.get("product", "nanobot")

    if request.file_path not in resources:
        raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")

    resources.pop(request.file_path)
    u.harness_sync_up(
        user_id=path, agent_id=name, product=product, resources=resources
    )
    return {
        "success": True,
        "data": {
            "deleted": request.file_path,
            "files": len(resources),
        },
    }


@router.get("/agents/{path}/{name}/repo/files")
async def list_repo_files(
    path: str,
    name: str,
    Revision: str = Query("", description="Branch or revision (unused; latest)"),
    Recursive: str = Query("true", description="Recurse into subdirectories"),
    Root: str = Query("", description="Root directory path to list under"),
    PageNumber: int = Query(1, ge=1, description="Page number"),
    PageSize: int = Query(100, ge=1, le=1000, description="Items per page"),
    user: dict = Depends(get_current_user),
):
    _ensure_owner(path, user)
    u = _ultron()
    profile = _get_profile_or_404(u, path, name)
    resources = profile.get("resources", {})

    root = Root.strip("/")
    prefix = f"{root}/" if root else ""
    recursive = Recursive.lower() not in ("false", "0", "no")

    entries = []
    for rel_path, content in resources.items():
        if prefix and not rel_path.startswith(prefix):
            continue
        remainder = rel_path[len(prefix):]
        if not recursive and "/" in remainder:
            continue
        entries.append(
            {
                "Path": rel_path,
                "Name": rel_path.rsplit("/", 1)[-1],
                "Type": "file",
                "Size": len(content.encode("utf-8")),
            }
        )

    entries.sort(key=lambda e: e["Path"])
    total = len(entries)
    start = (PageNumber - 1) * PageSize
    page = entries[start : start + PageSize]
    return {
        "success": True,
        "data": {
            "Files": page,
            "Total": total,
            "PageNumber": PageNumber,
            "PageSize": PageSize,
        },
    }


# ---- 4.2 Get file download ----


@router.get("/agents/{path}/{name}/repo")
async def get_repo_file(
    path: str,
    name: str,
    FilePath: str = Query(..., description="File path within the repo"),
    Revision: str = Query("", description="Branch or revision (unused; latest)"),
    user: dict = Depends(get_current_user),
):
    _ensure_owner(path, user)
    u = _ultron()
    profile = _get_profile_or_404(u, path, name)
    resources = profile.get("resources", {})
    if FilePath not in resources:
        raise HTTPException(status_code=404, detail="File not found")
    content = resources[FilePath]
    return {
        "success": True,
        "data": {
            "Path": FilePath,
            "Size": len(content.encode("utf-8")),
            "Encoding": "base64",
            "Content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        },
    }
