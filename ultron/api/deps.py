# Copyright (c) ModelScope Contributors. All rights reserved.
from fastapi import HTTPException, Request

from ultron import server_state


async def get_current_user(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or invalid Authorization header"
        )
    token = auth_header[7:]
    auth = server_state.auth_service
    u = server_state.ultron
    if auth is None or u is None:
        raise HTTPException(status_code=500, detail="Server not initialized")
    try:
        username = auth.decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = u.db.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
