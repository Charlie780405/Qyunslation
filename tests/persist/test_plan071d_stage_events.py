# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base, TranslationRunRecord, TranslationStageEvent
from qyunslation.pipeline.event_store import (
    StaleGenerationError,
    completed_stages,
    list_events,
    pending_stages,
    persist_buffer,
)
from qyunslation.pipeline.events import StageEventBuffer


@pytest.fixture()
def session():
    reset_engine()
    Base.metadata.create_all(init_engine("sqlite+pysqlite:///:memory:"))
    from qyunslation.persist.db import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
        reset_engine()


def _run(session, *, generation: int = 1) -> TranslationRunRecord:
    columns = {c.name: c for c in TranslationRunRecord.__table__.columns}
    values = {}
    for name, col in columns.items():
        if col.nullable or col.default is not None or col.server_default is not None:
            continue
        values[name] = 1 if "Integer" in type(col.type).__name__ else f"v-{name}"[: getattr(col.type, "length", None) or 40]
    values.update(id="run-1", generation=generation)
    run = TranslationRunRecord(**values)
    session.add(run)
    session.commit()
    return run


def test_sequence_is_monotonic_and_unique_constraint_enforced(session):
    run = _run(session)
    buf = StageEventBuffer()
    buf.emit_stage_start("validation")
    buf.emit_stage_complete("validation")
    persist_buffer(session, run_id=run.id, generation=1, buffer=buf)
    rows = list_events(session, run_id=run.id, generation=1)
    assert [r.sequence for r in rows] == [1, 2]
    session.add(
        TranslationStageEvent(run_id=run.id, generation=1, sequence=2, stage="text", state="running")
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_stale_generation_events_are_rejected(session):
    run = _run(session, generation=2)
    buf = StageEventBuffer()
    buf.emit_stage_start("text")
    with pytest.raises(StaleGenerationError):
        persist_buffer(session, run_id=run.id, generation=1, buffer=buf)
    assert list_events(session, run_id=run.id) == []


def test_resume_skips_completed_and_skipped_stages(session):
    run = _run(session)
    buf = StageEventBuffer()
    buf.emit_stage_complete("validation")
    buf.emit_stage_complete("structure")
    buf.emit_stage_skip("ocr", message="text pdf")
    buf.emit_stage_start("text")
    persist_buffer(session, run_id=run.id, generation=1, buffer=buf)
    assert completed_stages(session, run_id=run.id, generation=1) == {"validation", "structure", "ocr"}
    planned = ["validation", "structure", "ocr", "text", "table_figure", "layout"]
    assert pending_stages(session, run_id=run.id, generation=1, planned=planned) == [
        "text",
        "table_figure",
        "layout",
    ]


def test_units_progress_with_and_without_denominator(session):
    run = _run(session)
    buf = StageEventBuffer()
    buf.emit_stage_progress("ocr", units_done=3, units_total=12, message="3/12 页")
    buf.emit_stage_progress("text", units_done=5, units_total=None)
    persist_buffer(session, run_id=run.id, generation=1, buffer=buf)
    ocr, text = list_events(session, run_id=run.id, generation=1)
    assert (ocr.units_done, ocr.units_total, ocr.progress) == (3, 12, 25.0)
    assert (text.units_done, text.units_total, text.progress) == (5, None, None)


def test_cli_completion_is_not_export_progress():
    from qyunslation.pipeline.progress import cli_progress_is_text_only

    assert cli_progress_is_text_only("translating page 3")
    assert not cli_progress_is_text_only("export finished")
