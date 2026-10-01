# SPDX-License-Identifier: MPL-2.0
"""PLAN-072b：运行中阶段事件落库。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from qyunslation.pipeline.event_store import persist_buffer
from qyunslation.pipeline.events import StageEventBuffer


def persist_stage_snapshot(
    session: Session,
    *,
    run_id: str,
    generation: int,
    stage: str,
    state: str,
    message: str = "",
    progress: float | None = None,
    units_done: int | None = None,
    units_total: int | None = None,
) -> None:
    buf = StageEventBuffer()
    buf.emit(
        stage,
        state,
        message=message,
        progress=progress,
        units_done=units_done,
        units_total=units_total,
    )
    persist_buffer(session, run_id=run_id, generation=generation, buffer=buf)
