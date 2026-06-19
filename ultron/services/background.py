# Copyright (c) ModelScope Contributors. All rights reserved.
"""Long-running background jobs: trajectory, memory, evolution, SFT (wired from server lifespan)."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

_logger = logging.getLogger("ultron.services.background")


def run_pipeline_cycle(ultron_instance, *, sft_trainer=None) -> dict:
    """One full pipeline cycle: segment -> label -> extract -> rebalance -> evolve -> consolidate.

    Usable from both server (async decay loop) and client (watcher sync call).
    Returns a summary dict of what was done.
    """
    results: dict = {}

    ts = ultron_instance.trajectory_service
    if ts is not None:
        try:
            seg_result = ts.segment_pending_sessions()
            results["segmented"] = seg_result.get("segmented", 0)
            if seg_result.get("segmented"):
                _logger.info("Trajectory segmentation completed: %s", seg_result)
        except Exception:
            _logger.exception("Trajectory segmentation failed")
        try:
            label_result = ts.label_pending_segments()
            results["labeled"] = label_result.get("labeled", 0)
            if label_result.get("labeled"):
                _logger.info("Trajectory metric analysis completed: %s", label_result)
        except Exception:
            _logger.exception("Trajectory metric analysis failed")
        try:
            extract_result = ts.extract_memories_from_segments()
            results["extracted"] = extract_result.get("extracted", 0)
            if extract_result.get("extracted"):
                _logger.info(
                    "Trajectory memory extraction completed: %s", extract_result
                )
        except Exception:
            _logger.exception("Trajectory memory extraction failed")

    try:
        summary = ultron_instance.run_tier_rebalance()
        results["rebalance"] = summary
        _logger.info("Background tier rebalance completed: %s", summary)
    except Exception:
        _logger.exception("Background tier rebalance failed")

    evolution_engine = getattr(ultron_instance, "evolution_engine", None)
    if ultron_instance.config.evolution_enabled and evolution_engine:
        try:
            evo_result = evolution_engine.run_evolution_cycle()
            results["evolution"] = evo_result
            if evo_result.get("crystallized") or evo_result.get("recrystallized"):
                _logger.info("Background evolution completed: %s", evo_result)
        except Exception:
            _logger.exception("Background evolution cycle failed")

    if ultron_instance.config.consolidate_enabled:
        try:
            consolidate_result = ultron_instance.memory_service.consolidate_memories()
            results["consolidation"] = consolidate_result
            if consolidate_result["merges"] > 0:
                _logger.info("Background consolidation completed: %s", consolidate_result)
        except Exception:
            _logger.exception("Background consolidation failed")

    if sft_trainer is not None and sft_trainer.should_trigger():
        try:
            sft_result = sft_trainer.run_training()
            results["sft"] = sft_result
            _logger.info("SFT self-evolution completed: %s", sft_result)
        except Exception:
            _logger.exception("SFT self-evolution failed")

    return results


async def run_decay_loop() -> None:
    """Periodic job: runs run_pipeline_cycle at configured interval."""
    from ultron import server_state

    u = server_state.ultron
    if u is None:
        return
    interval = u.config.decay_interval_hours * 3600
    while True:
        await asyncio.sleep(interval)
        run_pipeline_cycle(u, sft_trainer=server_state.sft_trainer)
