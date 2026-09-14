# SPDX-License-Identifier: MPL-2.0
"""PLAN-050e：QA 条目与导出门禁。"""
from __future__ import annotations

from typing import Any

_BLOCKING = frozenset({"ERROR", "BLOCKING", "HARD"})


def qa_items(manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(manifest, dict):
        return []
    raw = manifest.get("issues") if isinstance(manifest.get("issues"), list) else []
    out: list[dict[str, Any]] = []
    for issue in raw:
        if not isinstance(issue, dict) or not issue.get("code"):
            continue
        sev = str(issue.get("severity") or "INFO").upper()
        level = "blocking" if sev in _BLOCKING else ("warning" if sev == "WARNING" else "info")
        out.append(
            {
                "code": str(issue["code"]),
                "level": level,
                "severity": sev,
                "object_id": issue.get("object_id"),
                "message": str(issue.get("message") or issue["code"]),
                "retryable": bool(issue.get("retryable")),
            }
        )
    return out


def export_gate(items: list[dict[str, Any]]) -> dict[str, Any]:
    blocking = [i for i in items if i.get("level") == "blocking"]
    return {
        "formal_export": len(blocking) == 0,
        "review_export": True,
        "blocking_count": len(blocking),
        "warning_count": sum(1 for i in items if i.get("level") == "warning"),
    }
