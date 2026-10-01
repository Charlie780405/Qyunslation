# SPDX-License-Identifier: MPL-2.0
"""PLAN-071b：内存阶段事件钩子（持久化由 071d 接管）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class StageEvent:
    sequence: int
    stage: str
    state: str
    message: str = ""
    progress: float | None = None
    at: str = field(default_factory=_utc_now)
    extra: dict[str, Any] = field(default_factory=dict)


class StageEventBuffer:
    """In-process ordered events; later flushed to translation_stage_event."""

    def __init__(self) -> None:
        self._events: list[StageEvent] = []
        self._seq = 0

    def emit(
        self,
        stage: str,
        state: str,
        *,
        message: str = "",
        progress: float | None = None,
        **extra: Any,
    ) -> StageEvent:
        self._seq += 1
        event = StageEvent(
            sequence=self._seq,
            stage=stage,
            state=state,
            message=message,
            progress=progress,
            extra=extra,
        )
        self._events.append(event)
        return event

    @property
    def events(self) -> list[StageEvent]:
        return list(self._events)

    def last_for(self, stage: str) -> StageEvent | None:
        for event in reversed(self._events):
            if event.stage == stage:
                return event
        return None
