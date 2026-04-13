# Copyright (c) ModelScope Contributors. All rights reserved.
import json
import logging
import math
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from ...config import UltronConfig, default_config
from ...core.models import MemoryRecord, MemoryTier, MemoryStatus
from ...core.database import Database
from ...core.embeddings import EmbeddingService
from ...utils.sanitizer import DataSanitizer
from ...utils.memory_type_infer import infer_memory_type
from ...utils.token_budget import get_token_counter, truncate_text_to_token_limit
from ...utils.intent_analyzer import IntentAnalyzer
from ...core.logging import log_event

logger = logging.getLogger(__name__)


@dataclass
class MemorySearchResult:
    """Search result wrapping a MemoryRecord with similarity scores."""

    record: MemoryRecord
    similarity_score: float
    tier_boosted_score: float

    def to_dict(self, *, include_embedding: bool = True) -> dict:
        result = self.record.to_dict(include_embedding=include_embedding)
        result["similarity_score"] = round(self.similarity_score, 4)
        result["tier_boosted_score"] = round(self.tier_boosted_score, 4)
        return result


class MemoryService:
    """
    Shared memory management service for multi-agent collective learning.

    Handles upload (with dedup/merge), semantic search, percentile-based tier
    rebalancing, and event-driven skill generation.

    Tiers: HOT (top N%) / WARM (next M%) / COLD (rest) — redistributed
    periodically by hit_count ranking via run_tier_rebalance().
    Status: active (default) / archived (before TTL deletion).
    """

    # Dedup scans all tiers including COLD to prevent semantic duplicates
    _DEDUP_SCAN_TIERS = (
        MemoryTier.HOT.value,
        MemoryTier.WARM.value,
        MemoryTier.COLD.value,
    )

    # Tier boost factors for search scoring
    TIER_BOOST = {"hot": 1.2, "warm": 1.0, "cold": 0.8}

    _MERGE_BLOCK_SEP = "\n\n---\n\n"
    # Near-duplicate merge: existing tags first, then incoming; case-insensitive dedup; hard cap
    _MERGED_TAGS_CAP = 10

    def __init__(
        self,
        database: Database,
        embedding_service: EmbeddingService,
        sanitizer: Optional[DataSanitizer] = None,
        config: Optional[UltronConfig] = None,
        llm_service=None,
        llm_orchestrator=None,
        skill_generator=None,
    ):
        self.db = database
        self.embedding = embedding_service
        self.sanitizer = sanitizer or DataSanitizer()
        self.config = config or default_config
        self.llm_service = llm_service
        self.llm_orchestrator = llm_orchestrator
        self.skill_generator = skill_generator
        self.intent_analyzer = IntentAnalyzer(llm_service=llm_service)
        self._merge_count_tokens = get_token_counter(
            self.config.llm_token_count_encoding
        )

    def _truncate_layer_text(self, text: str, max_tokens: int) -> str:
        """Truncate text to L0/L1 token limit (0 = no limit)."""
        if not text:
            return ""
        if max_tokens <= 0:
            return text
        return truncate_text_to_token_limit(text, max_tokens, self._merge_count_tokens)

    def _resolve_memory_type_auto(
        self, content: str, context: str, resolution: str
    ) -> str:
        """Infer memory_type: LLM first, keyword heuristic fallback."""
        if self.llm_orchestrator is not None:
            try:
                inferred = self.llm_orchestrator.classify_memory_type(
                    content, context, resolution
                )
                if inferred:
                    return inferred
            except Exception:
                pass
        return infer_memory_type(content, context, resolution)

    def _complete_near_duplicate_upload(
        self,
        existing: dict,
        memory_type: str,
        sanitized_content: str,
        sanitized_context: str,
        sanitized_resolution: str,
        tags: Optional[List[str]],
    ) -> Optional[MemoryRecord]:
        """
        Record hit, merge body/tags, refresh embedding and summaries when text
        changed, or update tags only; return the row if load succeeds.
        """
        mem_id = existing["id"]
        log_event(
            f"Near-duplicate hit: {mem_id[:8]}",
            action="upload_memory.dedup_hit",
            memory_id=mem_id,
        )
        updated_dict = self.db.increment_memory_hit(
            mem_id,
            content=sanitized_content,
            context=sanitized_context,
            resolution=sanitized_resolution,
        )

        existing_rec = MemoryRecord.from_dict(existing)
        merged_content, merged_context, merged_resolution = self._merge_memory_fields(
            existing_rec.content,
            existing_rec.context,
            existing_rec.resolution,
            sanitized_content,
            sanitized_context,
            sanitized_resolution,
        )
        merged_tags = self._merge_tags_lists(existing_rec.tags, tags)

        text_changed = (
            merged_content != existing_rec.content
            or merged_context != existing_rec.context
            or merged_resolution != existing_rec.resolution
        )
        tags_changed = merged_tags != existing_rec.tags

        if text_changed:
            new_embedding = self.embedding.embed_memory_context(
                memory_type=memory_type,
                content=merged_content,
                context=merged_context,
                resolution=merged_resolution,
            )
            summary_l0, overview_l1 = self._generate_summaries(
                merged_content,
                merged_context,
                merged_resolution,
            )
            self.db.update_memory_merged_body(
                mem_id,
                merged_content,
                merged_context,
                merged_resolution,
                new_embedding,
                summary_l0,
                overview_l1,
                tags=merged_tags,
            )
        elif tags_changed:
            emb = existing_rec.embedding or []
            self.db.update_memory_merged_body(
                mem_id,
                existing_rec.content,
                existing_rec.context,
                existing_rec.resolution,
                emb,
                existing_rec.summary_l0,
                existing_rec.overview_l1,
                tags=merged_tags,
            )

        refreshed = self.db.get_memory_record(mem_id)
        return MemoryRecord.from_dict(refreshed) if refreshed else None

    def upload_memory(
        self,
        content: str,
        context: str,
        resolution: str,
        tags: Optional[List[str]] = None,
    ) -> MemoryRecord:
        """
        Ingest one memory: sanitize, infer ``memory_type`` (callers cannot set it),
        embed, and either merge into a near-duplicate (same ``memory_type``,
        cosine similarity above ``dedup_similarity_threshold``) or insert WARM/ACTIVE.
        """
        _t0 = time.time()

        sanitized_content = self.sanitizer.sanitize(content)
        sanitized_context = self.sanitizer.sanitize(context)
        sanitized_resolution = self.sanitizer.sanitize(resolution)

        memory_type = self._resolve_memory_type_auto(
            sanitized_content, sanitized_context, sanitized_resolution
        )

        embedding = self.embedding.embed_memory_context(
            memory_type=memory_type,
            content=sanitized_content,
            context=sanitized_context,
            resolution=sanitized_resolution,
        )

        existing_result = self._find_near_duplicate(embedding, memory_type)
        if existing_result:
            existing, similarity = existing_result
            hard_threshold = self.config.dedup_similarity_threshold
            should_merge = similarity >= hard_threshold
            # Soft match: ask LLM to confirm before merging
            if not should_merge and self.llm_orchestrator is not None:
                try:
                    should_merge = self.llm_orchestrator.confirm_memory_duplicate(
                        existing.get("content", ""),
                        existing.get("context", ""),
                        sanitized_content,
                        sanitized_context,
                    )
                except Exception:
                    pass
            if should_merge:
                merged = self._complete_near_duplicate_upload(
                    existing,
                    memory_type,
                    sanitized_content,
                    sanitized_context,
                    sanitized_resolution,
                    tags,
                )
                if merged is not None:
                    return merged

        record_id = str(uuid.uuid4())
        now = datetime.now()

        summary_l0, overview_l1 = self._generate_summaries(
            sanitized_content,
            sanitized_context,
            sanitized_resolution,
        )

        record = MemoryRecord(
            id=record_id,
            memory_type=memory_type,
            content=sanitized_content,
            context=sanitized_context,
            resolution=sanitized_resolution,
            tier=MemoryTier.WARM.value,
            hit_count=1,
            status=MemoryStatus.ACTIVE.value,
            created_at=now,
            last_hit_at=now,
            embedding=embedding,
            tags=tags or [],
            summary_l0=summary_l0,
            overview_l1=overview_l1,
        )

        self.db.save_memory_record(record)
        _dur = round((time.time() - _t0) * 1000, 1)
        log_event(
            f"New memory created: {record_id[:8]}",
            action="upload_memory.created",
            memory_id=record_id,
            detail=f"type={memory_type}, tier=warm, l0={summary_l0[:40]}",
            duration_ms=_dur,
        )
        return record

    _DETAIL_CLEAR = {
        "l0": {"content", "context", "resolution", "overview_l1", "embedding"},
        "l1": {"content", "resolution", "embedding"},
    }

    _SEARCH_DETAIL_LEVELS = frozenset(_DETAIL_CLEAR.keys())

    def search_memories(
        self,
        query: str,
        tier: Optional[str] = None,
        limit: Optional[int] = None,
        detail_level: str = "l0",
    ) -> List[MemorySearchResult]:
        """
        Semantic search over memories with HOT tier boosting and time decay.

        Args:
            tier: None (default) = HOT+WARM, "hot"/"warm"/"cold" = specific, "all" = everything
            limit: Max rows; when omitted uses ``config.memory_search_default_limit``
            detail_level: "l0" / "l1" only; full text via ``get_memory_details``
        """
        eff_limit = (
            self.config.memory_search_default_limit if limit is None else max(1, limit)
        )
        if detail_level not in self._SEARCH_DETAIL_LEVELS:
            raise ValueError(
                "detail_level must be 'l0' or 'l1'; use get_memory_details(ids) for full content."
            )
        queries = (
            self.intent_analyzer.analyze(query)
            if self.config.enable_intent_analysis
            else [query]
        )
        query_embeddings = [self.embedding.embed_text(q) for q in queries]

        if tier == "all" or tier is None:
            tiers_to_search = [
                None
            ]  # All tiers; COLD ranks lower via tier boost + time decay
        elif tier:
            tiers_to_search = [tier]

        all_records = []
        for t in tiers_to_search:
            all_records.extend(self.db.get_memory_records_with_embeddings(tier=t))

        if not all_records:
            return []

        decay_w = self.config.time_decay_weight
        seen_ids: set = set()
        results: List[MemorySearchResult] = []
        clear_fields = self._DETAIL_CLEAR.get(detail_level, set())

        for memory_dict, emb in all_records:
            mid = memory_dict.get("id")
            if mid in seen_ids:
                continue
            seen_ids.add(mid)

            best_sim = max(
                (self.embedding.cosine_similarity(q, emb) for q in query_embeddings),
                default=0.0,
            )
            boost = self.TIER_BOOST.get(memory_dict.get("tier", "warm"), 1.0)
            hotness = self._calculate_hotness(memory_dict.get("last_hit_at"))
            score = best_sim * boost * (1.0 - decay_w + decay_w * hotness)

            record = MemoryRecord.from_dict(memory_dict)
            for field in clear_fields:
                setattr(record, field, [] if field == "embedding" else "")

            results.append(
                MemorySearchResult(
                    record=record,
                    similarity_score=max(0.0, best_sim),
                    tier_boosted_score=max(0.0, score),
                )
            )

        results.sort(key=lambda x: x.tier_boosted_score, reverse=True)
        results = results[:eff_limit]

        log_event(
            f"Memory search done: {len(results)}/{len(all_records)}",
            action="search_memories",
            query=query[:60],
            count=len(results),
            detail=f"detail_level={detail_level}, queries={len(queries)}",
        )
        self._record_adoption_hits(results, weight=1)

        return results

    @staticmethod
    def _record_embedding_vector(record: dict) -> List[float]:
        """Normalize record['embedding'] to a float list (handles legacy pickled bytes)."""
        raw = record.get("embedding")
        if not raw:
            return []
        if isinstance(raw, list):
            return raw
        try:
            import pickle

            out = pickle.loads(raw)
            return out if isinstance(out, list) else []
        except (TypeError, Exception):
            return []

    def get_memory_details(self, memory_ids: List[str]) -> List[MemoryRecord]:
        """Get memory details by IDs. Details is the strongest adoption signal, increment hit_count by 2."""
        results = []
        for mid in memory_ids:
            updated = self.db.increment_memory_hit_light(mid, weight=2)
            if updated:
                results.append(MemoryRecord.from_dict(updated))
        return results

    def run_tier_rebalance(self) -> dict:
        """
        Percentile-based tier redistribution.

        Ranks all active memories by hit_count DESC, last_hit_at DESC, then
        assigns tiers by configurable percentiles (default: top 10% HOT,
        next 40% WARM, rest COLD). Memories newly entering HOT trigger
        skill generation. Stale COLD records are deleted by TTL.
        """
        ranked = self.db.get_all_memory_ids_ranked()
        total = len(ranked)

        hot_count = (
            math.ceil(total * self.config.hot_percentile / 100) if total > 0 else 0
        )
        warm_count = (
            math.ceil(total * self.config.warm_percentile / 100) if total > 0 else 0
        )

        updates: list = []
        newly_hot: list = []

        for i, (mid, old_tier) in enumerate(ranked):
            if i < hot_count:
                new_tier = MemoryTier.HOT.value
            elif i < hot_count + warm_count:
                new_tier = MemoryTier.WARM.value
            else:
                new_tier = MemoryTier.COLD.value

            if new_tier != old_tier:
                updates.append((mid, new_tier))
                if (
                    new_tier == MemoryTier.HOT.value
                    and old_tier != MemoryTier.HOT.value
                ):
                    newly_hot.append(mid)

        changed = self.db.batch_update_tiers(updates)

        # Trigger skill generation for memories newly entering HOT
        for mid in newly_hot:
            self._try_auto_generate_skill(mid)

        # COLD TTL → archive (excluded from search and future rebalance)
        cold_archived = 0
        if self.config.cold_ttl_days > 0:
            cold_archived = self.db.archive_stale_cold_memories(
                self.config.cold_ttl_days
            )

        summary = {
            "total": total,
            "hot": hot_count,
            "warm": warm_count,
            "cold": max(total - hot_count - warm_count, 0),
            "tier_changes": changed,
            "newly_hot": len(newly_hot),
            "cold_archived": cold_archived,
        }

        if changed > 0 or cold_archived > 0:
            log_event(
                f"Tier rebalance done: {changed} changes, {cold_archived} archived",
                action="tier_rebalance",
                detail=json.dumps(summary, ensure_ascii=False),
            )
        return summary

    def get_promotion_candidates(self) -> List[MemoryRecord]:
        """HOT memories eligible to be distilled into a skill."""
        return [MemoryRecord.from_dict(c) for c in self.db.get_promotion_candidates()]

    def get_memory_stats(self) -> dict:
        """Aggregate counts: total memories and breakdown by tier, type, and status."""
        return self.db.get_memory_stats()

    # ============ Consolidation (chain-merge) ============

    def consolidate_memories(
        self, *, max_merges: Optional[int] = None, dry_run: bool = False
    ) -> dict:
        """Scan all active memories and merge near-duplicates that were missed at upload time.

        Handles two scenarios:
        1. Parallel uploads that raced past dedup detection.
        2. Chain merges are handled across successive consolidation runs —
           each run merges the current best pairs; the next run picks up any
           new pairs created by embedding drift.

        Pre-computes all candidate pairs in one batch (numpy), then processes
        them greedily from highest to lowest similarity.

        Args:
            max_merges: Override ``consolidate_max_merges`` config for this run.
            dry_run: If True, only report what would be merged without executing.

        Returns a summary dict with merge count and details.
        """
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
        # Phase 1: find all candidate pairs in one shot
        candidates = self._find_all_consolidation_pairs(soft)
        if not candidates:
            logger.info("consolidation: done (no candidate pairs above soft threshold)")
            return {"merges": 0, "details": []}

        logger.info(
            "consolidation: phase1 done candidate_pairs=%d (phase2 merge cap=%d)",
            len(candidates),
            limit,
        )

        # Phase 2: greedily merge from highest similarity down
        merged_ids: set = set()
        total_merged = 0
        merge_log: list = []
        total_candidates = len(candidates)
        _phase2_log_interval = max(1, min(100, total_candidates // 20 or 1))

        for idx, (winner_dict, loser_dict, similarity) in enumerate(candidates, start=1):
            if total_merged >= limit:
                break
            # Skip if either record was already consumed in this run
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

            # In dry_run, only process hard matches (skip LLM calls)
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
                # In dry_run, skip soft matches (would need LLM)
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
        """Find all pairs above threshold across all active memories (same type).

        Uses numpy matrix multiplication for fast batch cosine similarity.
        Returns a list of ``(winner_dict, loser_dict, similarity)`` sorted by
        similarity descending.  The winner is the record with higher hit_count.
        """
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

            # Only upper triangle (avoid duplicates and self-comparison)
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

        # Sort by similarity descending — merge the most similar first
        all_pairs.sort(key=lambda x: x[2], reverse=True)
        return all_pairs

    def _execute_consolidation_merge(self, winner: dict, loser: dict) -> None:
        """Merge loser into winner: combine fields, re-embed, re-summarize, archive loser.

        Uses rule-based merge and summary generation (no LLM calls) to keep
        consolidation fast.  Only the embedding API is called remotely.
        """
        winner_rec = MemoryRecord.from_dict(winner)
        loser_rec = MemoryRecord.from_dict(loser)

        # Rule-based merge (skip LLM to avoid slow API calls)
        merged_content = self._merge_pair_fields(
            winner_rec.content,
            loser_rec.content,
        )
        merged_context = self._merge_pair_fields(
            winner_rec.context,
            loser_rec.context,
        )
        merged_resolution = self._merge_pair_fields(
            winner_rec.resolution,
            loser_rec.resolution,
        )
        merged_tags = self._merge_tags_lists(winner_rec.tags, loser_rec.tags)

        # Accumulate hit_count from loser
        loser_hits = loser_rec.hit_count or 0
        if loser_hits > 0:
            self.db.increment_memory_hit(
                winner["id"],
                content="",
                context="",
                resolution="",
            )

        # Re-embed (fast API call)
        new_embedding = self.embedding.embed_memory_context(
            memory_type=winner_rec.memory_type,
            content=merged_content,
            context=merged_context,
            resolution=merged_resolution,
        )

        # Rule-based summaries (no LLM)
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

        # Archive the loser
        self.db.update_memory_status(loser["id"], MemoryStatus.ARCHIVED.value)

    def _generate_summaries_rule(
        self, content: str, context: str, resolution: str
    ) -> tuple:
        """Rule-based L0/L1 generation only (no LLM). Used by consolidation for speed."""
        l0m = self.config.l0_max_tokens
        l1m = self.config.l1_max_tokens
        ct = self._merge_count_tokens

        # L0: content collapsed to single line
        l0 = ""
        for src in (content, context, resolution):
            if src and src.strip():
                flat = " ".join(l.strip() for l in src.split("\n") if l.strip())
                l0 = self._truncate_layer_text(flat, l0m)
                break

        # L1: content (70%) + context (15%) + resolution (15%)
        parts = []
        if content:
            brief = " ".join(l.strip() for l in content.split("\n") if l.strip())
            if l1m > 0:
                brief = truncate_text_to_token_limit(brief, max(int(l1m * 0.70), 1), ct)
            parts.append(brief)
        if context:
            cx = (
                truncate_text_to_token_limit(context, max(int(l1m * 0.15), 1), ct)
                if l1m > 0
                else context
            )
            parts.append(cx)
        if resolution:
            rx = (
                truncate_text_to_token_limit(resolution, max(int(l1m * 0.15), 1), ct)
                if l1m > 0
                else resolution
            )
            parts.append(rx)

        l1 = self._truncate_layer_text("\n".join(parts), l1m)
        return l0, l1

    # ============ Quality Control ============

    def _cap_merge_field_by_tokens(self, text: str) -> str:
        max_t = self.config.memory_merge_max_field_tokens
        if max_t <= 0 or not text:
            return text
        return truncate_text_to_token_limit(text, max_t, self._merge_count_tokens)

    @staticmethod
    def _collapse_ws(s: str) -> str:
        return " ".join((s or "").split())

    def _merge_pair_fields(self, existing: str, incoming: str) -> str:
        """Merge one field pair: if one text subsumes the other keep the longer;
        else join with a separator block.

        When concatenation would exceed 80% of the merge token cap, keep the
        longer text instead — repeated concatenation that gets hard-truncated
        produces garbled walls of text.
        """
        ex = (existing or "").strip()
        inc = (incoming or "").strip()
        if not inc:
            return ex
        if not ex:
            return self._cap_merge_field_by_tokens(inc)
        ex_n = self._collapse_ws(ex)
        inc_n = self._collapse_ws(inc)
        if inc_n in ex_n or inc in ex:
            return self._cap_merge_field_by_tokens(ex)
        if ex_n in inc_n or ex in inc:
            return self._cap_merge_field_by_tokens(inc)
        # Guard against unbounded growth: if the concatenation would be close
        # to the cap, just keep the longer piece intact rather than producing
        # a truncated wall of text.
        max_t = self.config.memory_merge_max_field_tokens
        if max_t > 0:
            merged_len_estimate = self._merge_count_tokens(
                ex
            ) + self._merge_count_tokens(inc)
            if merged_len_estimate > int(max_t * 0.8):
                longer = ex if len(ex) >= len(inc) else inc
                return self._cap_merge_field_by_tokens(longer)
        merged = ex + self._MERGE_BLOCK_SEP + inc
        return self._cap_merge_field_by_tokens(merged)

    def _merge_memory_fields(
        self,
        old_content: str,
        old_context: str,
        old_resolution: str,
        new_content: str,
        new_context: str,
        new_resolution: str,
    ) -> tuple:
        """Merge two memories: LLM abstraction first, regex fallback on failure."""
        if self.llm_orchestrator is not None:
            try:
                merged = self.llm_orchestrator.merge_memories(
                    old_content,
                    old_context,
                    old_resolution,
                    new_content,
                    new_context,
                    new_resolution,
                    max_field_tokens=self.config.memory_merge_max_field_tokens,
                )
                if merged:
                    return (
                        self._cap_merge_field_by_tokens(
                            merged.get("content", "") or old_content
                        ),
                        self._cap_merge_field_by_tokens(
                            merged.get("context", "") or old_context
                        ),
                        self._cap_merge_field_by_tokens(
                            merged.get("resolution", "") or old_resolution
                        ),
                    )
            except Exception:
                pass
        return (
            self._merge_pair_fields(old_content, new_content),
            self._merge_pair_fields(old_context, new_context),
            self._merge_pair_fields(old_resolution, new_resolution),
        )

    @staticmethod
    def _merge_tags_lists(
        existing: Optional[List[str]],
        incoming: Optional[List[str]],
    ) -> List[str]:
        """
        Merge tag lists for near-duplicate hits: existing first, then incoming.
        Dedupe is case-insensitive (first spelling wins); at most MemoryService._MERGED_TAGS_CAP tags.
        """
        cap = MemoryService._MERGED_TAGS_CAP
        seen_keys: set = set()
        out: List[str] = []
        for t in list(existing or []) + list(incoming or []):
            t = (t or "").strip()
            if not t:
                continue
            key = t.casefold()
            if key in seen_keys:
                continue
            seen_keys.add(key)
            out.append(t)
            if len(out) >= cap:
                break
        return out

    def _record_adoption_hits(
        self, results: List[MemorySearchResult], weight: int = 1
    ) -> None:
        """Record adoption hits for search results (hit_count only, no tier change)."""
        for r in results:
            mid = r.record.id
            if not mid:
                continue
            self.db.increment_memory_hit_light(mid, weight=weight)

    def _find_near_duplicate(
        self,
        embedding: List[float],
        memory_type: str,
    ) -> Optional[tuple]:
        """
        Find the best near-duplicate in the same memory_type.

        Returns ``(memory_dict, similarity)`` if the best cosine similarity
        is >= ``dedup_soft_threshold``, else ``None``.
        All tiers (HOT, WARM, COLD) are scanned to prevent semantic duplicates.
        """
        soft = self.config.dedup_soft_threshold
        best_match: Optional[dict] = None
        best_similarity = 0.0

        for tier in self._DEDUP_SCAN_TIERS:
            rows = self.db.get_memory_records_with_embeddings(
                memory_type=memory_type,
                tier=tier,
            )
            for memory_dict, existing_embedding in rows:
                sim = self.embedding.cosine_similarity(embedding, existing_embedding)
                if sim >= soft and sim > best_similarity:
                    best_similarity = sim
                    best_match = memory_dict

        if best_match is not None:
            return best_match, best_similarity
        return None

    def _generate_summaries(self, content: str, context: str, resolution: str) -> tuple:
        """Generate L0 (one-line) and L1 (overview) summaries. LLM first, rule fallback."""
        l0m = self.config.l0_max_tokens
        l1m = self.config.l1_max_tokens

        # Try LLM
        if self.llm_orchestrator is not None:
            try:
                result = self.llm_orchestrator.summarize_for_l0_l1(
                    content,
                    context,
                    resolution,
                    l0_max_tokens=l0m,
                    l1_max_tokens=l1m,
                )
                if result and result.get("summary_l0"):
                    return result["summary_l0"], result.get("overview_l1", "")
            except Exception:
                pass

        # Rule fallback: L0 = content collapsed to single line, truncated to
        # sentence boundary.  Falls back to context / resolution if empty.
        ct = self._merge_count_tokens
        l0 = ""
        for src in (content, context, resolution):
            if src and src.strip():
                flat = " ".join(l.strip() for l in src.split("\n") if l.strip())
                l0 = self._truncate_layer_text(flat, l0m)
                break

        # Rule fallback: L1 = content (70%) + context (15%) + resolution (15%)
        # Each part is independently truncated to sentence boundary, then joined
        # by newline.  No mechanical prefixes like "Context:" to avoid wasting
        # tokens and producing ugly truncated labels.
        parts = []
        if content:
            brief = " ".join(l.strip() for l in content.split("\n") if l.strip())
            if l1m > 0:
                brief = truncate_text_to_token_limit(brief, max(int(l1m * 0.70), 1), ct)
            parts.append(brief)
        if context:
            cx = (
                truncate_text_to_token_limit(context, max(int(l1m * 0.15), 1), ct)
                if l1m > 0
                else context
            )
            parts.append(cx)
        if resolution:
            rx = (
                truncate_text_to_token_limit(resolution, max(int(l1m * 0.15), 1), ct)
                if l1m > 0
                else resolution
            )
            parts.append(rx)

        l1 = self._truncate_layer_text("\n".join(parts), l1m)
        return l0, l1

    def _calculate_hotness(self, last_hit_at) -> float:
        """Continuous time decay: hotness = exp(-alpha * days_since_last_hit). Returns 0.0~1.0."""
        if last_hit_at is None:
            return 0.0
        if isinstance(last_hit_at, str):
            try:
                last_hit_at = datetime.fromisoformat(last_hit_at)
            except (ValueError, TypeError):
                return 0.0
        days = max((datetime.now() - last_hit_at).total_seconds() / 86400.0, 0)
        return math.exp(-self.config.decay_alpha * days)

    def _try_auto_generate_skill(self, memory_id: str) -> None:
        """Attempt skill generation for a memory newly entering HOT. Failures are silent."""
        if not self.skill_generator:
            return
        try:
            self.skill_generator.generate_skill_from_memory(memory_id)
        except Exception:
            pass
