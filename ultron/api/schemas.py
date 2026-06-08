# Copyright (c) ModelScope Contributors. All rights reserved.
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class UploadMemoryRequest(BaseModel):
    content: str = Field(..., description="Memory content")
    context: str = Field("", description="Context / scenario")
    resolution: str = Field("", description="Resolution / solution")
    tags: List[str] = Field([], description="Tags")


class SearchMemoryRequest(BaseModel):
    query: str = Field(
        ..., description="Natural language query (searches across all memory types)"
    )
    tier: Optional[str] = Field(
        None, description="Tier filter: hot/warm/cold/all (default HOT+WARM)"
    )
    limit: Optional[int] = Field(
        None,
        description="Max results; omitted uses server config (ULTRON_MEMORY_SEARCH_LIMIT, default 10)",
    )
    detail_level: Literal["l0", "l1"] = Field(
        "l0",
        description="Snippet level: l0 or l1 only; full text via POST /memory/details",
    )


class MemoryDetailsRequest(BaseModel):
    memory_ids: List[str] = Field(..., description="Memory IDs selected by the model")


class IngestRequest(BaseModel):
    paths: List[str] = Field(..., description="File or directory paths")
    agent_id: str = Field(
        ..., description="Unique agent identifier for progress isolation"
    )


class IngestTextRequest(BaseModel):
    text: str = Field(..., description="Raw text content")


class SearchSkillsRequest(BaseModel):
    query: str = Field(..., description="Natural language query")
    limit: Optional[int] = Field(
        None,
        description="Max results; omitted uses server config (ULTRON_SKILL_SEARCH_LIMIT, default 5)",
    )


class UploadSkillsRequest(BaseModel):
    paths: List[str] = Field(..., description="Skill directory paths")


class InstallSkillRequest(BaseModel):
    full_name: str = Field(
        ..., description="Catalog skill full name (e.g. @namespace/skill-name)"
    )
    target_dir: str = Field(
        ...,
        description="Target directory to copy the skill to (e.g. ~/.nanobot/workspace/skills)",
    )


class RegisterUserRequest(BaseModel):
    username: str = Field(
        ..., min_length=3, max_length=32, description="Username (3-32 chars)"
    )
    password: str = Field(
        ..., min_length=6, max_length=128, description="Password (min 6 chars)"
    )


class LoginRequest(BaseModel):
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")


class SyncUpRequest(BaseModel):
    agent_id: str = Field(..., description="Agent/terminal identifier")
    product: str = Field("nanobot", description="Claw product: nanobot/openclaw/hermes")
    resources: dict = Field(..., description="Workspace files {relative_path: content}")


class SyncDownRequest(BaseModel):
    agent_id: str = Field(..., description="Device/terminal identifier")


class CreateShareRequest(BaseModel):
    agent_id: str = Field(..., description="Device/terminal identifier")
    visibility: str = Field("public", description="Stored as public (legacy clients may omit)")


class DeleteShareRequest(BaseModel):
    token: str = Field(..., description="Share token to delete")


class DeleteAgentRequest(BaseModel):
    agent_id: str = Field(..., description="Agent/terminal identifier")


# ---- Repository API (ModelScope-hub style, /api/v1/agents/*) ----


class CreateRepoRequest(BaseModel):
    """Create an agent repository. Maps to a (user_id, agent_id) harness profile."""

    Path: str = Field(..., description="Repo path (user/org); must match the caller")
    Name: str = Field(..., description="Repo name; stored as agent_id")
    Framework: str = Field(
        ..., description="Framework/product, e.g. OpenClaw / QwenPaw / nanobot"
    )
    Visibility: str = Field("public", description="Visibility: public / private")


class LfsObject(BaseModel):
    oid: str = Field(..., description="File SHA256 hash")
    size: int = Field(..., description="File size in bytes")


class LfsBatchRequest(BaseModel):
    operation: str = Field("upload", description="Fixed value: upload")
    objects: List[LfsObject] = Field(..., description="File object list")


class CommitAction(BaseModel):
    action: str = Field(..., description="Operation: update / delete")
    path: str = Field(..., description="File path within the repo")
    type: str = Field(
        "normal", description="File type: normal (regular) / lfs (large)"
    )
    size: int = Field(0, description="File size in bytes")
    sha256: str = Field("", description="SHA256 (required for lfs, may be empty)")
    content: str = Field(
        "", description="Content: base64 for normal files, empty for lfs"
    )
    encoding: str = Field(
        "", description="Encoding: base64 for normal files, empty for lfs"
    )


class CommitRequest(BaseModel):
    commit_message: str = Field(..., description="Commit message")
    actions: List[CommitAction] = Field(..., description="File operation list")
