# Copyright (c) ModelScope Contributors. All rights reserved.
"""Parse trajectory ``quality_metrics`` JSON; derive score and task type for display and filters."""
from __future__ import annotations

import json
from typing import Any, Optional

__all__ = [
    "parse_segment_quality_json",
    "overall_score_unit_from_assessment",
    "task_type_from_assessment",
    "enrich_task_segment_row",
    "enrich_trajectory_row",
    "json_summary_overall_score_norm_sql",
]


def parse_segment_quality_json(seg: dict) -> dict[str, Any]:
    raw = seg.get("quality_metrics") or ""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_json_str(raw: str) -> dict[str, Any]:
    if not (raw and str(raw).strip()):
        return {}
    try:
        p = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return p if isinstance(p, dict) else {}


def overall_score_unit_from_assessment(assessment: dict[str, Any]) -> Optional[float]:
    """
    Return ``summary.overall_score`` clamped to [0, 1], or None if missing.

    ms-agent computes ``overall_score`` as a 0-1 aggregate (``TrajectoryAnalysisAgent._overall_score``);
    metric prompts also use 0-1. No percent-scale conversion is applied here.
    """
    summary = assessment.get("summary")
    if not isinstance(summary, dict):
        return None
    raw = summary.get("overall_score")
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, v))


def task_type_from_assessment(assessment: dict[str, Any]) -> str:
    summary = assessment.get("summary")
    if not isinstance(summary, dict):
        return "other"
    return str(summary.get("task_type") or "other")


def enrich_task_segment_row(row: dict) -> dict:
    """Set ``quality_score`` and ``task_type`` from ``quality_metrics`` (source of truth)."""
    a = _parse_json_str(str(row.get("quality_metrics") or ""))
    if a:
        row = dict(row)
        row["quality_score"] = overall_score_unit_from_assessment(a)
        row["task_type"] = task_type_from_assessment(a)
    else:
        row = dict(row)
        row["quality_score"] = None
        row["task_type"] = "other"
    return row


def enrich_trajectory_row(row: dict) -> dict:
    """Same enrichment for ``trajectory_records`` rows."""
    return enrich_task_segment_row(row)


def json_summary_overall_score_norm_sql() -> str:
    """
    SQL expression: read ``summary.overall_score`` and clamp to [0, 1] (ms-agent is 0-1).
    NULL if ``overall_score`` is absent.
    """
    j = "json_extract(quality_metrics, '$.summary.overall_score')"
    return (
        f"(CASE WHEN {j} IS NULL THEN NULL "
        f"ELSE MIN(1.0, MAX(0.0, CAST({j} AS REAL))) END)"
    )
