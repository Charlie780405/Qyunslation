# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base, PreflightRecord, Tenant, TranslationRunRecord
from qyunslation.pipeline.event_store import (
    completed_stages,
    persist_buffer,
    should_skip_stage,
)
from qyunslation.pipeline.events import StageEventBuffer


@pytest.fixture()
def session(monkeypatch):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    reset_engine()


def test_completed_stages_skip_on_resume(session: Session):
    tenant = Tenant(slug="pilot", name="Pilot")
    session.add(tenant)
    session.flush()
    preflight = PreflightRecord(
        tenant_id=tenant.id,
        actor_sub="u1",
        source_filename="a.pdf",
        source_format="pdf",
        source_sha256="a" * 64,
        size_bytes=10,
        storage_key="k",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    session.add(preflight)
    session.flush()
    run = TranslationRunRecord(
        preflight_id=preflight.id,
        tenant_id=tenant.id,
        actor_sub="u1",
        idempotency_key_hash="h1",
        generation=1,
        direction="en-zh",
        profile="clinical",
        status="translating",
        stage="text",
    )
    session.add(run)
    session.flush()
    buf = StageEventBuffer()
    buf.emit("validation", "completed", message="ok")
    buf.emit("structure", "completed", message="ok")
    persist_buffer(session, run_id=run.id, generation=1, buffer=buf)
    session.commit()
    assert completed_stages(session, run_id=run.id, generation=1) == {
        "validation",
        "structure",
    }
    assert should_skip_stage(session, run_id=run.id, generation=1, stage="validation")
    assert not should_skip_stage(session, run_id=run.id, generation=1, stage="text")
