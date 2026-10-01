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
    units_done: int | None = None
    units_total: int | None = None
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
        units_done: int | None = None,
        units_total: int | None = None,
        **extra: Any,
    ) -> StageEvent:
        self._seq += 1
        if progress is None and units_total:
            from qyunslation.pipeline.progress import progress_for_units

            progress = progress_for_units(units_done=units_done, units_total=units_total)
        event = StageEvent(
            sequence=self._seq,
            stage=stage,
            state=state,
            message=message,
            progress=progress,
            units_done=units_done,
            units_total=units_total,
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

    def emit_stage_start(self, stage: str, *, message: str = "", **extra: Any) -> StageEvent:
        return self.emit(stage, "running", message=message, **extra)

    def emit_stage_progress(
        self,
        stage: str,
        *,
        units_done: int | None,
        units_total: int | None,
        message: str = "",
    ) -> StageEvent:
        """无可靠分母时 progress 保持 None（UI 显示不确定进度）。"""
        return self.emit(
            stage, "running", message=message, units_done=units_done, units_total=units_total
        )

    def emit_stage_complete(self, stage: str, *, message: str = "", **extra: Any) -> StageEvent:
        return self.emit(stage, "completed", message=message, progress=100.0, **extra)

    def emit_stage_skip(self, stage: str, *, message: str = "", **extra: Any) -> StageEvent:
        return self.emit(stage, "skipped", message=message, **extra)

    def emit_stage_fail(
        self, stage: str, *, error_code: str, message: str = "", **extra: Any
    ) -> StageEvent:
        return self.emit(stage, "failed", message=message, error_code=error_code, **extra)
