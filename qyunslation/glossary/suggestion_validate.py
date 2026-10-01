# SPDX-License-Identifier: MPL-2.0
"""PLAN-071h：术语建议 JSON Schema 校验。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    path = Path(__file__).with_name("suggestion_schema.json")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_suggestion(payload: dict[str, Any]) -> tuple[bool, str | None]:
    schema = _schema()
    if not isinstance(payload, dict):
        return False, "not_object"
    for key in schema.get("required") or []:
        if key not in payload:
            return False, f"missing:{key}"
    target = payload.get("target")
    if not isinstance(target, str) or not target.strip():
        return False, "empty_target"
    try:
        conf = float(payload.get("confidence"))
    except (TypeError, ValueError):
        return False, "bad_confidence"
    if conf < 0 or conf > 1:
        return False, "confidence_range"
    risk = payload.get("risk")
    if risk not in {"low", "normal", "high", "critical"}:
        return False, "bad_risk"
    return True, None
