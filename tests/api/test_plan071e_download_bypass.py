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
from qyunslation.persist.models import Base, TranslationArtifact, TranslationRunRecord


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
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as current:
        yield current
    reset_engine()


def _headers():
    return {"X-Dev-User": "planner", "X-Dev-Tenant": "pilot"}


def test_formal_download_requires_approved(client, tmp_path: Path):
    preflight = client.post(
        "/api/v1/preflights",
        headers=_headers(),
        files={"file": ("protocol.pdf", b"%PDF-1.7", "application/pdf")},
    ).json()
    created = client.post(
        "/api/v1/translation-runs",
        headers={**_headers(), "Idempotency-Key": "dl-gate"},
        json={"preflight_id": preflight["id"]},
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_root / "formal.pdf"
    artifact_path.write_bytes(b"%PDF formal")
    assert persist_db.SessionLocal is not None
    with persist_db.SessionLocal() as session:
        run = session.scalar(select(TranslationRunRecord).where(TranslationRunRecord.id == run_id))
        assert run is not None
        run.status = "succeeded"
        run.quality_state = "review_ready"
        session.add(
            TranslationArtifact(
                run_id=run.id,
                tenant_id=run.tenant_id,
                artifact_key="formal",
                kind="formal",
                file_type="pdf",
                filename="formal.pdf",
                media_type="application/pdf",
                storage_key="formal.pdf",
                size_bytes=artifact_path.stat().st_size,
                sha256="b" * 64,
                formal_export=True,
            )
        )
        session.commit()
        artifact_id = session.scalar(
            select(TranslationArtifact.id).where(TranslationArtifact.run_id == run_id)
        )
    blocked = client.get(
        f"/api/v1/translation-runs/{run_id}/artifacts/{artifact_id}",
        headers=_headers(),
    )
    assert blocked.status_code == 409
