# Copyright (c) ModelScope Contributors. All rights reserved.
"""Memory consolidation mixin for batch near-duplicate merging."""
from __future__ import annotations

import json
import logging
import time
from typing import List, Optional

from ...core.logging import log_event
from ...core.models import MemoryRecord, MemoryStatus

logger = logging.getLogger(__name__)


class MemoryConsolidationMixin:
    """Batch consolidation operations for MemoryService."""

    def consolidate_memories(
        self, *, max_merges: Optional[int] = None, dry_run: bool = False
    ) -> dict:
        """Scan active memories and merge near-duplicates missed at upload time."""
        limit = (
            max_merges if max_merges is not None else self.config.consolidate_max_merges
        )
        hard = self.config.dedup_similarity_threshold
        soft = self.config.dedup_soft_threshold

        logger.info(
            "consolidation: start dry_run=%s max_merges=%d soft=%.3f hard=%.3f",
            dry_run,
            limit,
            soft,
            hard,
        )
        candidates = self._find_all_consolidation_pairs(soft)
        if not candidates:
            logger.info("consolidation: done (no candidate pairs above soft threshold)")
            return {"merges": 0, "details": []}

        logger.info(
            "consolidation: phase1 done candidate_pairs=%d (phase2 merge cap=%d)",
            len(candidates),
            limit,
        )

        merged_ids: set = set()
        total_merged = 0
        merge_log: list = []
        total_candidates = len(candidates)
        _phase2_log_interval = max(1, min(100, total_candidates // 20 or 1))

        for idx, (winner_dict, loser_dict, similarity) in enumerate(candidates, start=1):
            if total_merged >= limit:
                break
            if winner_dict["id"] in merged_ids or loser_dict["id"] in merged_ids:
                continue

            if idx == 1 or idx % _phase2_log_interval == 0:
                logger.info(
                    "consolidation: phase2 scanning pair %d/%d merges_so_far=%d/%d",
                    idx,
                    total_candidates,
                    total_merged,
                    limit,
                )

            if not dry_run and similarity < hard and self.llm_orchestrator is not None:
                logger.info(
                    "consolidation: phase2 LLM duplicate check pair=%d sim=%.3f",
                    idx,
                    similarity,
                )
                try:
                    confirmed = self.llm_orchestrator.confirm_memory_duplicate(
                        winner_dict.get("content", ""),
                        winner_dict.get("context", ""),
                        loser_dict.get("content", ""),
                        loser_dict.get("context", ""),
                    )
                except Exception:
                    confirmed = False
                if not confirmed:
                    continue
            elif dry_run and similarity < hard:
                continue

            if not dry_run:
                self._execute_consolidation_merge(winner_dict, loser_dict)
            merged_ids.add(loser_dict["id"])
            total_merged += 1
            logger.info(
                "consolidation: phase2 merged %d/%d sim=%.4f dry_run=%s",
                total_merged,
                limit,
                similarity,
                dry_run,
            )
            merge_log.append(
                {
                    "winner": winner_dict["id"][:8],
                    "loser": loser_dict["id"][:8],
                    "similarity": round(similarity, 4),
                    "winner_l0": (winner_dict.get("summary_l0") or "")[:60],
                    "loser_l0": (loser_dict.get("summary_l0") or "")[:60],
                }
            )

        if total_merged > 0:
            log_event(
                f"Consolidation done: {total_merged} merges",
                action="consolidate_memories",
                detail=json.dumps(merge_log, ensure_ascii=False),
            )
        logger.info(
            "consolidation: finished merges=%d dry_run=%s (pairs_examined up to cap)",
            total_merged,
            dry_run,
        )
        return {
            "merges": total_merged,
            "details": merge_log,
        }

    def _find_all_consolidation_pairs(
        self,
        threshold: float,
    ) -> List[tuple]:
        """Find all pairs above threshold across active same-type memories."""
        import numpy as np

        all_pairs: list = []
        phase1_t0 = time.perf_counter()

        for mtype in (
            "error",
            "security",
            "correction",
            "pattern",
            "preference",
            "life",
        ):
            rows = self.db.get_memory_records_with_embeddings(memory_type=mtype)
            n = len(rows)
            if n < 2:
                logger.info(
                    "consolidation: phase1 type=%s skip embeddings=%d (need >=2)",
                    mtype,
                    n,
                )
                continue

            logger.info(
                "consolidation: phase1 type=%s computing similarity matrix n=%d",
                mtype,
                n,
            )
            t_type = time.perf_counter()
            dicts = [r[0] for r in rows]
            mat = np.array([r[1] for r in rows], dtype=np.float32)
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            norms = np.maximum(norms, 1e-10)
            normed = mat / norms
            sim_matrix = normed @ normed.T

            np.fill_diagonal(sim_matrix, 0.0)
            indices = np.argwhere(np.triu(sim_matrix) >= threshold)

            pair_count = 0
            for idx in indices:
                i, j = int(idx[0]), int(idx[1])
                sim = float(sim_matrix[i, j])
                hi_i = dicts[i].get("hit_count", 0) or 0
                hi_j = dicts[j].get("hit_count", 0) or 0
                if hi_i >= hi_j:
                    all_pairs.append((dicts[i], dicts[j], sim))
                else:
                    all_pairs.append((dicts[j], dicts[i], sim))
                pair_count += 1

            logger.info(
                "consolidation: phase1 type=%s pairs_above_soft=%d elapsed=%.2fs",
                mtype,
                pair_count,
                time.perf_counter() - t_type,
            )

        logger.info(
            "consolidation: phase1 all types elapsed=%.2fs total_pairs=%d",
            time.perf_counter() - phase1_t0,
            len(all_pairs),
        )

        all_pairs.sort(key=lambda x: x[2], reverse=True)
        return all_pairs

    def _execute_consolidation_merge(self, winner: dict, loser: dict) -> None:
        """Merge loser into winner, refresh embedding/summaries, and archive loser."""
        winner_rec = MemoryRecord.from_dict(winner)
        loser_rec = MemoryRecord.from_dict(loser)

        merged_content, merged_context, merged_resolution = self._merge_memory_fields(
            winner_rec.content,
            winner_rec.context,
            winner_rec.resolution,
            loser_rec.content,
            loser_rec.context,
            loser_rec.resolution,
        )

        text_changed = (
            merged_content != winner_rec.content
            or merged_context != winner_rec.context
            or merged_resolution != winner_rec.resolution
        )
        if not text_changed:
            return

        merged_tags = self._merge_tags_lists(winner_rec.tags, loser_rec.tags)

        loser_hits = loser_rec.hit_count or 0
        if loser_hits > 0:
            self.db.increment_memory_hit(
                winner["id"],
                content="",
                context="",
                resolution="",
            )

        new_embedding = self.embedding.embed_memory_context(
            memory_type=winner_rec.memory_type,
            content=merged_content,
            context=merged_context,
            resolution=merged_resolution,
        )

        summary_l0, overview_l1 = self._generate_summaries_rule(
            merged_content,
            merged_context,
            merged_resolution,
        )

        self.db.update_memory_merged_body(
            winner["id"],
            merged_content,
            merged_context,
            merged_resolution,
            new_embedding,
            summary_l0,
            overview_l1,
            tags=merged_tags,
        )

        self.db.update_memory_status(loser["id"], MemoryStatus.ARCHIVED.value)
