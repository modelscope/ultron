# Copyright (c) ModelScope Contributors. All rights reserved.
import json
import logging
import secrets
import string
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_SHORT_CODE_ALPHABET = string.ascii_letters + string.digits
_SHORT_CODE_LENGTH = 6
_SHORT_CODE_MAX_RETRIES = 10


class HarnessService:
    """Orchestrates agent management, workspace sync, and profile sharing."""

    def __init__(self, db):
        self.db = db

    def _generate_short_code(self) -> str:
        """Generate a unique 6-char alphanumeric short code."""
        for _ in range(_SHORT_CODE_MAX_RETRIES):
            code = "".join(
                secrets.choice(_SHORT_CODE_ALPHABET)
                for _ in range(_SHORT_CODE_LENGTH)
            )
            if not self.db.get_share_by_code(code):
                return code
        raise RuntimeError("Failed to generate unique short code")

    def register_agent(
        self, user_id: str, agent_id: str, display_name: str = ""
    ) -> dict:
        return self.db.register_agent(user_id, agent_id, display_name)

    def list_agents(self, user_id: str) -> List[dict]:
        return self.db.list_agents(user_id)

    def remove_agent(self, user_id: str, agent_id: str) -> bool:
        return self.db.delete_agent(user_id, agent_id)

    def sync_up(
        self,
        user_id: str,
        agent_id: str,
        product: str,
        resources: Dict[str, str],
    ) -> dict:
        self.db.register_agent(user_id, agent_id)
        resources_json = json.dumps(resources, ensure_ascii=False)
        result = self.db.upsert_profile(user_id, agent_id, resources_json, product)
        # Keep share snapshots in sync with the latest profile.
        existing_share = self.db.get_share_by_agent(user_id, agent_id)
        if existing_share:
            snapshot = json.dumps(
                {"product": product, "resources": resources}, ensure_ascii=False
            )
            self.db.update_share_snapshot(existing_share["token"], snapshot)
        return result

    def sync_down(self, user_id: str, agent_id: str) -> Optional[dict]:
        return self.db.get_profile(user_id, agent_id)

    def create_share(
        self, user_id: str, agent_id: str, visibility: str = "public"
    ) -> dict:
        profile = self.db.get_profile(user_id, agent_id)
        if not profile:
            raise ValueError("No profile to share — sync up first")

        # Reuse existing share for the same agent, just refresh the snapshot.
        existing = self.db.get_share_by_agent(user_id, agent_id)
        snapshot = json.dumps(
            {
                "product": profile["product"],
                "resources": profile["resources"],
            },
            ensure_ascii=False,
        )
        if existing:
            return self.db.update_share_snapshot(existing["token"], snapshot)

        token = secrets.token_urlsafe(16)
        short_code = self._generate_short_code()
        return self.db.create_share(
            token, user_id, agent_id, visibility, snapshot, short_code
        )

    def get_share_by_code(self, short_code: str) -> Optional[dict]:
        return self.db.get_share_by_code(short_code)

    def get_profile(self, user_id: str, agent_id: str) -> Optional[dict]:
        return self.db.get_profile(user_id, agent_id)

    def get_profiles_by_user(self, user_id: str) -> list:
        return self.db.get_profiles_by_user(user_id)

    def list_shares(self, user_id: str) -> List[dict]:
        return self.db.list_shares_by_user(user_id)

    def delete_share(self, token: str) -> bool:
        return self.db.delete_share(token)


__all__ = ["HarnessService"]
