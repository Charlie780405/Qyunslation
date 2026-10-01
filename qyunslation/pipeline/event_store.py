# SPDX-License-Identifier: MPL-2.0
"""PLAN-071d：阶段事件持久化与 reconcile。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from qyunslation.persist.models import TranslationRunRecord, TranslationStageEvent
from qyunslation.pipeline.events import StageEvent, StageEventBuffer


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StaleGenerationError(RuntimeError):
    """事件的 generation 与任务当前 generation 不一致，拒绝写入。"""


def assert_current_generation(session: Session, *, run_id: str, generation: int) -> None:
    current = session.scalar(
        select(TranslationRunRecord.generation).where(TranslationRunRecord.id == run_id)
    )
    if current is None or int(current) != int(generation):
        raise StaleGenerationError(
            f"run {run_id} generation {generation} is not current ({current})"
        )


def next_sequence(session: Session, *, run_id: str, generation: int) -> int:
    current = session.scalar(
        select(TranslationStageEvent.sequence)
        .where(
            TranslationStageEvent.run_id == run_id,
            TranslationStageEvent.generation == generation,
        )
        .order_by(TranslationStageEvent.sequence.desc())
        .limit(1)
    )
    return int(current or 0) + 1


def persist_buffer(
    session: Session,
    *,
    run_id: str,
    generation: int,
    buffer: StageEventBuffer,
    start_sequence: int | None = None,
) -> list[TranslationStageEvent]:
    assert_current_generation(session, run_id=run_id, generation=generation)
    seq = start_sequence or next_sequence(session, run_id=run_id, generation=generation)
    rows: list[TranslationStageEvent] = []
    for event in buffer.events:
        # Skip if this sequence already exists (restart safety).
        existing = session.scalar(
            select(TranslationStageEvent).where(
                TranslationStageEvent.run_id == run_id,
                TranslationStageEvent.generation == generation,
                TranslationStageEvent.sequence == seq,
            )
        )
        if existing is not None:
            seq += 1
            continue
        finished = event.state in {"completed", "skipped", "failed", "blocked"}
        row = TranslationStageEvent(
            run_id=run_id,
            generation=generation,
            sequence=seq,
            stage=event.stage,
            state=event.state,
            started_at=_utcnow() if event.state == "running" else None,
            finished_at=_utcnow() if finished else None,
            progress=event.progress,
            units_done=event.units_done,
            units_total=event.units_total,
            message=(event.message or "")[:512] or None,
            error_code=str(event.extra.get("error_code") or "")[:64] or None,
            trace_id=str(event.extra.get("trace_id") or "")[:64] or None,
        )
        session.add(row)
        rows.append(row)
        seq += 1
    session.flush()
    return rows


def list_events(
    session: Session,
    *,
    run_id: str,
    generation: int | None = None,
    after_sequence: int = 0,
) -> list[TranslationStageEvent]:
    stmt = select(TranslationStageEvent).where(TranslationStageEvent.run_id == run_id)
    if generation is not None:
        stmt = stmt.where(TranslationStageEvent.generation == generation)
    if after_sequence:
        stmt = stmt.where(TranslationStageEvent.sequence > after_sequence)
    stmt = stmt.order_by(
        TranslationStageEvent.generation.asc(),
        TranslationStageEvent.sequence.asc(),
    )
    return list(session.scalars(stmt))


def completed_stages(
    session: Session, *, run_id: str, generation: int
) -> set[str]:
    rows = list_events(session, run_id=run_id, generation=generation)
    done: set[str] = set()
    for row in rows:
        if row.state in {"completed", "skipped"}:
            done.add(row.stage)
    return done


def should_skip_stage(
    session: Session, *, run_id: str, generation: int, stage: str
) -> bool:
    return stage in completed_stages(session, run_id=run_id, generation=generation)


def event_to_dict(row: TranslationStageEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "generation": row.generation,
        "sequence": row.sequence,
        "stage": row.stage,
        "state": row.state,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "progress": row.progress,
        "units_done": row.units_done,
        "units_total": row.units_total,
        "message": row.message,
        "error_code": row.error_code,
        "trace_id": row.trace_id,
    }


def pending_stages(
    session: Session, *, run_id: str, generation: int, planned: Iterable[str]
) -> list[str]:
    """重启 reconcile：已 completed/skipped 的阶段不再重复执行。"""
    done = completed_stages(session, run_id=run_id, generation=generation)
    return [stage for stage in planned if stage not in done]
