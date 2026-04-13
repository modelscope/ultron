# Copyright (c) ModelScope Contributors. All rights reserved.
"""Authentication service: password hashing (bcrypt) and JWT token management."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt


class AuthService:
    """Stateless auth helpers — instantiated with config values."""

    def __init__(self, secret: str, expire_hours: int = 24):
        self.secret = secret
        self.expire_hours = expire_hours
        self.algorithm = "HS256"

    # ---- Password ----

    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

    # ---- JWT ----

    def create_token(self, username: str) -> str:
        payload = {
            "sub": username,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=self.expire_hours),
        }
        return jwt.encode(payload, self.secret, algorithm=self.algorithm)

    def decode_token(self, token: str) -> str:
        """Return the username from a valid token. Raises jwt.PyJWTError on failure."""
        payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])
        username = payload.get("sub")
        if not username:
            raise jwt.InvalidTokenError("Missing 'sub' claim")
        return username
