# Copyright (c) ModelScope Contributors. All rights reserved.
from typing import List, Optional

from ...core.models import MemoryRecord
from ...services.memory import MemorySearchResult


class MemoryMixin:
    def upload_memory(
        self,
        content: str,
        context: str,
        resolution: str,
        tags: Optional[List[str]] = None,
    ) -> MemoryRecord:
        """
        Upload a memory to the shared remote memory store.

        Type is determined server-side by LLM (rule fallback); callers cannot specify type.
        Automatic dedup: near-duplicate hits increment the existing record.
        """
        return self.memory_service.upload_memory(
            content=content,
            context=context,
            resolution=resolution,
            tags=tags,
        )

    def search_memories(
        self,
        query: str,
        tier: Optional[str] = None,
        limit: Optional[int] = None,
        detail_level: str = "l0",
    ) -> List[MemorySearchResult]:
        """
        Semantic search over shared remote memories (all memory types).

        Scores blend cosine similarity, HOT-tier boost, and time decay.
        ``tier``: None → HOT+WARM; ``hot`` / ``warm`` / ``cold`` / ``all`` to restrict.
        ``limit``: When omitted, uses ``config.memory_search_default_limit`` (``ULTRON_MEMORY_SEARCH_LIMIT``).
        ``detail_level``: ``l0`` or ``l1`` snippets only; for full ``content`` fields call
        ``get_memory_details``.
        """
        return self.memory_service.search_memories(
            query=query,
            tier=tier,
            limit=limit,
            detail_level=detail_level,
        )

    def get_memory_details(self, memory_ids: List[str]) -> List[MemoryRecord]:
        """
        Second-stage fetch: full ``MemoryRecord`` rows for IDs chosen after search.

        Strong adoption signal: increments each record's hit counter (see MemoryService).
        """
        return self.memory_service.get_memory_details(memory_ids)

    def run_tier_rebalance(self) -> dict:
        """
        Run percentile-based tier redistribution.

        Ranks all active memories by hit_count and reassigns HOT/WARM/COLD
        tiers by configurable percentiles. Returns a summary dict with counts.
        """
        return self.memory_service.run_tier_rebalance()

    def get_memory_stats(self) -> dict:
        """Return aggregate memory counts (totals and breakdown by tier, type, and status)."""
        return self.memory_service.get_memory_stats()

    def ingest(
        self,
        paths: List[str],
        agent_id: str = "",
    ) -> dict:
        """
        Unified ingestion: accepts .jsonl file/directory paths.

        ``.jsonl`` files require ``trajectory_service`` and append to ``trajectory_records``
        (see Trajectory Hub). Use ``ingest_text`` for plain text. Directories are expanded
        recursively to nested ``.jsonl`` files (hidden path segments skipped).
        """
        return self.ingestion_service.ingest(paths=paths, agent_id=agent_id)

    def ingest_text(
        self,
        text: str,
    ) -> dict:
        """Ingest plain text; the LLM extracts candidate memories."""
        return self.ingestion_service.ingest_text(
            text=text,
        )
