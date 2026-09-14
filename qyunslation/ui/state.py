# SPDX-License-Identifier: MPL-2.0
"""PLAN-050c：任务状态机。未知不得伪装成 succeeded 或数字 0。"""
from __future__ import annotations

from typing import Any

TASK_STATES = (
    "queued",
    "scanning",
    "translating",
    "rendering",
    "review_ready",
    "succeeded",
    "failed",
    "cancelled",
    "blocked",
    "degraded",
)

_ALIASES = {
    "queue": "queued",
    "pending": "queued",
    "prescan": "scanning",
    "scan": "scanning",
    "translate": "translating",
    "running": "translating",
    "render": "rendering",
    "layout": "rendering",
    "review": "review_ready",
    "done": "succeeded",
    "success": "succeeded",
    "complete": "succeeded",
    "completed": "succeeded",
    "error": "failed",
    "fail": "failed",
    "cancel": "cancelled",
    "canceled": "cancelled",
    "timeout": "blocked",
    "truncated": "degraded",
    "unknown": "degraded",
}


def normalize_task_state(raw: Any) -> str:
    """把后端/进度文案收成 TASK_STATES；无法识别 → degraded（非 succeeded）。"""
    if raw is None:
        return "degraded"
    text = str(raw).strip().lower()
    if not text:
        return "degraded"
    if text in TASK_STATES:
        return text
    if text in _ALIASES:
        return _ALIASES[text]
    for token in TASK_STATES:
        if token in text:
            return token
    for alias, mapped in _ALIASES.items():
        if alias in text:
            return mapped
    return "degraded"


def is_terminal(state: str) -> bool:
    return normalize_task_state(state) in {
        "succeeded",
        "failed",
        "cancelled",
        "blocked",
    }
