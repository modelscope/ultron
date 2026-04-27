# Copyright (c) ModelScope Contributors. All rights reserved.
"""Long-running background jobs: trajectory, memory, evolution, SFT (wired from server lifespan)."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

_logger = logging.getLogger("ultron.services.background")


async def run_decay_loop() -> None:
    """Periodic job: trajectory labeling, memory extraction, rebalance, evolution, consolidation, SFT."""
    from ultron import server_state

    u = server_state.ultron
    if u is None:
        return
    interval = u.config.decay_interval_hours * 3600
    while True:
        await asyncio.sleep(interval)

        ts = server_state.trajectory_service
        if ts is not None:
            try:
                seg_result = ts.segment_pending_sessions()
                if seg_result.get("segmented"):
                    _logger.info("Trajectory segmentation completed: %s", seg_result)
            except Exception:
                _logger.exception("Trajectory segmentation failed")
            try:
                label_result = ts.label_pending_segments()
                if label_result.get("labeled"):
                    _logger.info("Trajectory metric analysis completed: %s", label_result)
            except Exception:
                _logger.exception("Trajectory metric analysis failed")
            try:
                extract_result = ts.extract_memories_from_segments()
                if extract_result.get("extracted"):
                    _logger.info(
                        "Trajectory memory extraction completed: %s", extract_result
                    )
            except Exception:
                _logger.exception("Trajectory memory extraction failed")

        try:
            summary = u.run_tier_rebalance()
            _logger.info("Background tier rebalance completed: %s", summary)
        except Exception:
            _logger.exception("Background tier rebalance failed")

        if u.config.evolution_enabled and server_state.evolution_engine:
            try:
                evo_result = server_state.evolution_engine.run_evolution_cycle()
                if evo_result.get("crystallized") or evo_result.get("recrystallized"):
                    _logger.info("Background evolution completed: %s", evo_result)
            except Exception:
                _logger.exception("Background evolution cycle failed")

        if u.config.consolidate_enabled:
            try:
                result = u.memory_service.consolidate_memories()
                if result["merges"] > 0:
                    _logger.info("Background consolidation completed: %s", result)
            except Exception:
                _logger.exception("Background consolidation failed")

        sft: Optional[object] = server_state.sft_trainer
        if sft is not None and sft.should_trigger():
            try:
                sft_result = sft.run_training()
                _logger.info("SFT self-evolution completed: %s", sft_result)
            except Exception:
                _logger.exception("SFT self-evolution failed")
