# Copyright (c) ModelScope Contributors. All rights reserved.
"""SFT self-evolution via Twinkle Train-as-a-Service.

Monitors SFT-eligible trajectory increments and triggers LoRA fine-tuning
on ModelScope Twinkle when the accumulated count reaches the configured
threshold (default 1000).  Each run resumes from the last saved checkpoint
so the model continuously improves as new trajectories flow in.

Requires optional dependencies (not part of the default install)::

    pip install 'twinkle-kit' 'tinker' tqdm datasets torch

Set ``MODELSCOPE_TOKEN`` to your API key from https://www.modelscope.cn/my/access/token
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...config import UltronConfig, default_config
from ...core.database import Database
from .sft_exporter import SFTExporter

logger = logging.getLogger(__name__)


def _normalize_model_id(raw: str) -> tuple[str, str]:
    """Return ``(ms:// prefixed id, bare model id)``."""
    s = (raw or "").strip()
    if s.startswith("ms://"):
        return s, s[len("ms://") :]
    return f"ms://{s}", s


class SFTTrainerService:
    """Twinkle LoRA SFT trainer driven by SFTExporter exports.

    Lifecycle (called from the periodic background scheduler):

    1. ``should_trigger`` — SFT-eligible segment delta vs ``sft_trigger_threshold``.
    2. ``run_training`` — ``export_sft_since``, JSONL, Twinkle TaaS, checkpoint.
    """

    def __init__(
        self,
        db: Database,
        sft_exporter: SFTExporter,
        config: Optional[UltronConfig] = None,
    ):
        self.db = db
        self.sft_exporter = sft_exporter
        self.config = config or default_config

    def should_trigger(self) -> bool:
        """Return True when enough SFT-eligible segments have accumulated."""
        if not self.config.sft_enabled:
            return False
        min_s = float(getattr(self.config, "trajectory_sft_score_threshold", 0.8))
        delta = self.db.get_sft_eligible_segment_count_since_last_sft(
            min_quality_score=min_s,
        )
        return delta >= self.config.sft_trigger_threshold

    def run_training(self) -> Dict[str, Any]:
        """Export incremental trajectories, run Twinkle LoRA SFT, and save the checkpoint."""
        cfg = self.config
        since = self.db.get_last_sft_finished_at()
        min_s = float(getattr(self.config, "trajectory_sft_score_threshold", 0.8))
        eligible_count = self.db.get_sft_eligible_segment_count_since_last_sft(
            min_quality_score=min_s,
        )
        record_id = str(uuid.uuid4())
        parent_ckpt = self.db.get_latest_sft_checkpoint() or ""

        records = self.sft_exporter.export_sft_since(since=since)
        if not records:
            logger.info("SFT skipped: no new eligible trajectories to export")
            return {"status": "skipped", "reason": "no_new_eligible_trajectories"}

        jsonl_path = cfg.sft_dir / f"sft_{record_id[:8]}.jsonl"
        self._write_jsonl(jsonl_path, records)
        logger.info("Exported %d SFT samples to %s", len(records), jsonl_path)

        self.db.save_sft_training_record(
            record_id=record_id,
            eligible_count=eligible_count,
            samples_exported=len(records),
            base_model=cfg.sft_base_model,
            parent_checkpoint=parent_ckpt,
            epochs=cfg.sft_epochs,
            status="running",
        )

        try:
            checkpoint = self._twinkle_train(jsonl_path, parent_ckpt)
        except Exception as e:
            logger.exception("SFT training failed")
            self.db.update_sft_training_status(
                record_id, status="failed", error_message=str(e)[:500],
            )
            return {"status": "failed", "record_id": record_id, "error": str(e)}

        self.db.update_sft_training_status(
            record_id, status="completed", checkpoint_path=checkpoint,
        )
        logger.info(
            "SFT training completed: record=%s, checkpoint=%s, samples=%d",
            record_id[:8], checkpoint, len(records),
        )
        return {
            "status": "completed",
            "record_id": record_id,
            "checkpoint": checkpoint,
            "samples": len(records),
        }

    def _twinkle_train(self, jsonl_path: Path, parent_checkpoint: str) -> str:
        """Run LoRA SFT via Twinkle TaaS client. Returns the saved checkpoint path."""
        try:
            from tqdm import tqdm
            from tinker import types
            from twinkle_client import init_tinker_client
            from twinkle.data_format import Trajectory  # noqa: F401
            from twinkle.dataloader import DataLoader
            from twinkle.dataset import Dataset, DatasetMeta
            from twinkle.server.common import input_feature_to_datum
        except ImportError as e:
            raise RuntimeError(
                "Missing Twinkle dependencies. Install via: "
                "pip install 'twinkle-kit' 'tinker' tqdm datasets torch"
            ) from e

        api_key = os.environ.get("MODELSCOPE_TOKEN", "").strip()
        if not api_key:
            raise RuntimeError(
                "MODELSCOPE_TOKEN not set. "
                "Get your key at https://www.modelscope.cn/my/access/token"
            )

        cfg = self.config
        base_model, base_model_id = _normalize_model_id(cfg.sft_base_model)

        dataset = Dataset(dataset_meta=DatasetMeta(str(jsonl_path)))
        dataset.set_template(
            "Qwen3_5Template",
            model_id=base_model,
            max_length=cfg.sft_max_length,
            truncation_strategy="left",
            default_system=cfg.sft_system_prompt,
        )
        dataset.encode(batched=True, load_from_cache_file=False)
        dataloader = DataLoader(
            dataset=dataset,
            batch_size=max(1, cfg.sft_batch_size),
            drop_last=True,
        )

        init_tinker_client()
        from tinker import ServiceClient  # noqa: E402

        service_client = ServiceClient(base_url=cfg.sft_base_url, api_key=api_key)
        training_client = service_client.create_lora_training_client(
            base_model=base_model_id,
            rank=cfg.sft_lora_rank,
        )

        if parent_checkpoint:
            try:
                training_client.load_state(parent_checkpoint)
                logger.info("Resumed from checkpoint: %s", parent_checkpoint)
            except Exception as e:
                logger.warning("Could not load parent checkpoint %s: %s", parent_checkpoint, e)

        last_checkpoint = ""
        for epoch in range(cfg.sft_epochs):
            logger.info("SFT epoch %d/%d", epoch + 1, cfg.sft_epochs)
            for _, batch in tqdm(
                enumerate(dataloader),
                total=len(dataloader),
                desc=f"epoch {epoch}",
            ):
                input_datum = [input_feature_to_datum(f) for f in batch]
                fwd_future = training_client.forward_backward(input_datum, "cross_entropy")
                opt_future = training_client.optim_step(
                    types.AdamParams(learning_rate=cfg.sft_learning_rate),
                )
                fwd_future.result()
                opt_result = opt_future.result()
                logger.debug("Training step metrics: %s", opt_result)

            save = training_client.save_state(
                f"ultron-sft-epoch{epoch}",
            ).result()
            last_checkpoint = save.path
            logger.info("Saved epoch %d checkpoint: %s", epoch, last_checkpoint)

        return last_checkpoint

    @staticmethod
    def _write_jsonl(path: Path, records: List[Dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for row in records:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
