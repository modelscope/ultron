# Copyright (c) ModelScope Contributors. All rights reserved.
from typing import List, Optional


class HarnessMixin:
    def list_agents(self, user_id: str) -> List[dict]:
        """List all registered agents for a user."""
        return self.harness.list_agents(user_id)

    def remove_agent(self, user_id: str, agent_id: str) -> bool:
        """Remove an agent and cascade-delete its profile and shares."""
        return self.harness.remove_agent(user_id, agent_id)

    def harness_sync_up(
        self,
        user_id: str,
        agent_id: str,
        product: str,
        resources: dict,
    ) -> dict:
        """Upload a workspace bundle to the server."""
        return self.harness.sync_up(user_id, agent_id, product, resources)

    def harness_sync_down(self, user_id: str, agent_id: str) -> Optional[dict]:
        """Download the stored workspace bundle for a (user, agent) pair."""
        return self.harness.sync_down(user_id, agent_id)

    def get_harness_profile(self, user_id: str, agent_id: str) -> Optional[dict]:
        """Get the harness profile for a (user, agent) pair."""
        return self.harness.get_profile(user_id, agent_id)

    def get_profiles_by_user(self, user_id: str) -> list:
        """List all workspace profiles for a user."""
        return self.harness.get_profiles_by_user(user_id)

    def create_harness_share(
        self, user_id: str, agent_id: str, visibility: str = "public"
    ) -> dict:
        """Create a share token from the current profile."""
        return self.harness.create_share(user_id, agent_id, visibility)

    def list_harness_shares(self, user_id: str) -> List[dict]:
        """List all share tokens created by a user."""
        return self.harness.list_shares(user_id)

    def delete_harness_share(self, token: str) -> bool:
        """Delete a share token."""
        return self.harness.delete_share(token)
