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
from qyunslation.persist.models import Base, DocumentTermCandidate, PreflightRecord, TranslationRunRecord
from qyunslation.workbench.term_extract import extract_candidates_from_text


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
    monkeypatch.setenv("QYUNSLATION_TERM_SUGGEST", "0")
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as current:
        yield current
    reset_engine()


def _headers(user="reviewer"):
    return {"X-Dev-User": user, "X-Dev-Tenant": "pilot", "X-Dev-Role": "reviewer"}


def test_enrich_suggestions_backfills_pending_candidates(client, monkeypatch):
    monkeypatch.setenv("QYUNSLATION_TERM_SUGGEST", "1")

    class _SuggestProvider:
        def translate(self, source, *, system=None):
            return '[{"source_term":"IL-4","observed_target":"","suggested_target":"白细胞介素-4","confidence":0.9}]'

    preflight = client.post(
        "/api/v1/preflights",
        headers=_headers(),
        files={"file": ("protocol.pdf", b"%PDF-1.7", "application/pdf")},
    ).json()
    created = client.post(
        "/api/v1/translation-runs",
        headers={**_headers(), "Idempotency-Key": "enrich-run"},
        json={"preflight_id": preflight["id"]},
    )
    run_id = created.json()["id"]
    assert persist_db.SessionLocal is not None
    with persist_db.SessionLocal() as session:
        run = session.get(TranslationRunRecord, run_id)
        pre = session.get(PreflightRecord, run.preflight_id)
        extract_candidates_from_text(
            session,
            run=run,
            preflight=pre,
            source_text="Dupilumab inhibits IL-4 signaling.",
            translated_text="度普利尤单抗抑制 IL-4 信号。",
            provider=_SuggestProvider(),
        )
        rows = list(
            session.scalars(
                select(DocumentTermCandidate).where(
                    DocumentTermCandidate.translation_run_id == run_id
                )
            ).all()
        )
        il4 = next(row for row in rows if row.source_term == "IL-4")
        il4.suggested_target = None
        session.commit()

    monkeypatch.setattr(
        "qyunslation.workbench.term_extract.resolve_term_provider",
        lambda run, explicit=None: _SuggestProvider(),
    )
    enriched = client.post(
        f"/api/v1/translation-runs/{run_id}/term-candidates/enrich-suggestions",
        headers=_headers(),
    )
    assert enriched.status_code == 200, enriched.text
    payload = enriched.json()
    assert payload["suggestions_enriched"] >= 1
    il4 = next(item for item in payload["items"] if item["source_term"] == "IL-4")
    assert il4["suggested_target"] == "白细胞介素-4"
