# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist import db as persist_db
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base, TranslationRunRecord


@pytest.fixture()
def client(monkeypatch, tmp_path: Path):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    monkeypatch.setenv("QYUNSLATION_PREFLIGHT_ROOT", str(tmp_path / "preflights"))
    monkeypatch.setenv("QYUNSLATION_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("QYUNSLATION_RUNNER_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("QYUNSLATION_PIPELINE_ROOT", str(tmp_path / "pipeline"))
    monkeypatch.setenv("QYUNSLATION_PIPELINE", "legacy")
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as current:
        yield current
    reset_engine()


def _headers(user="reviewer"):
    return {"X-Dev-User": user, "X-Dev-Tenant": "pilot", "X-Dev-Role": "reviewer"}


def test_cannot_approve_with_blockers(client):
    preflight = client.post(
        "/api/v1/preflights",
        headers=_headers(),
        files={"file": ("protocol.pdf", b"%PDF-1.7", "application/pdf")},
    ).json()
    created = client.post(
        "/api/v1/translation-runs",
        headers={**_headers(), "Idempotency-Key": "qa-block"},
        json={"preflight_id": preflight["id"]},
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]
    assert persist_db.SessionLocal is not None
    with persist_db.SessionLocal() as session:
        run = session.scalar(select(TranslationRunRecord).where(TranslationRunRecord.id == run_id))
        assert run is not None
        run.quality_state = "qa_blocked"
        run.qa_summary = {"blocker": 1, "warning": 0, "info": 0}
        run.status = "review_ready"
        session.commit()
    denied = client.post(
        f"/api/v1/translation-runs/{run_id}/review-decision",
        headers=_headers("reviewer"),
        json={"decision": "approve"},
    )
    assert denied.status_code == 409
