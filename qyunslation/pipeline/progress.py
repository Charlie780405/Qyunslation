# SPDX-License-Identifier: MPL-2.0
"""PLAN-071d：按工作单元计算阶段进度。"""
from __future__ import annotations

from typing import Any


def progress_for_units(*, units_done: int | None, units_total: int | None) -> float | None:
    """Return 0–100 progress, or None when denominator is unreliable."""
    if units_total is None or units_total <= 0:
        return None
    done = max(0, int(units_done or 0))
    return round(min(100.0, (done / float(units_total)) * 100.0), 2)


def stage_unit_denominator(stage: str, *, counts: dict[str, Any] | None = None) -> int | None:
    counts = counts or {}
    key = {
        "ocr": "pages",
        "text": "text_objects",
        "table_figure": "table_figure_objects",
        "layout": "pages",
        "qa": "qa_checks",
    }.get(stage)
    if not key:
        return None
    value = counts.get(key)
    try:
        total = int(value)
    except (TypeError, ValueError):
        return None
    return total if total > 0 else None


def cli_progress_is_text_only(label: str) -> bool:
    """CLI completion lines map only to text-stage subprogress, never export."""
    text = (label or "").casefold()
    if "export" in text or "qa" in text or "review" in text:
        return False
    return True
