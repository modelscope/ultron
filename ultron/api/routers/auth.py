# Copyright (c) ModelScope Contributors. All rights reserved.
from fastapi import APIRouter, Depends, HTTPException

from ultron import server_state
from ultron.api.deps import get_current_user
from ultron.api.schemas import LoginRequest, RegisterUserRequest

router = APIRouter(tags=["auth"])


@router.post("/auth/register")
async def auth_register(request: RegisterUserRequest):
    auth = server_state.auth_service
    u = server_state.ultron
    if auth is None or u is None:
        raise RuntimeError("Server not initialized")
    password_hash = auth.hash_password(request.password)
    try:
        user = u.db.create_user(
            username=request.username,
            password_hash=password_hash,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    token = auth.create_token(user["username"])
    return {
        "success": True,
        "data": {
            "username": user["username"],
            "token": token,
        },
    }


@router.post("/auth/login")
async def auth_login(request: LoginRequest):
    auth = server_state.auth_service
    u = server_state.ultron
    if auth is None or u is None:
        raise RuntimeError("Server not initialized")
    user = u.db.get_user_by_username(request.username)
    if not user or not auth.verify_password(
        request.password, user["password_hash"]
    ):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = auth.create_token(user["username"])
    return {
        "success": True,
        "data": {
            "username": user["username"],
            "token": token,
        },
    }


@router.get("/auth/me")
async def auth_me(user: dict = Depends(get_current_user)):
    return {
        "success": True,
        "data": {
            "username": user["username"],
            "created_at": user["created_at"],
        },
    }
