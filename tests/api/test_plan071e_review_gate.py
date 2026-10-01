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
from qyunslation.persist.models import Base, PreflightRecord, TranslationRunRecord


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


def test_term_review_payload_and_formal_gate_require_every_candidate_decision(client):
    from qyunslation.workbench.term_extract import extract_candidates_from_text

    run_id = _make_run(client, "term-review-gate")
    with persist_db.SessionLocal() as session:
        run = session.get(TranslationRunRecord, run_id)
        preflight = session.get(PreflightRecord, run.preflight_id)
        run.quality_state = "review_ready"
        run.qa_summary = {"blocker": 0, "warning": 0, "info": 0}
        rows = extract_candidates_from_text(
            session,
            run=run,
            preflight=preflight,
            source_text="Vitiligo improved after treatment.",
            translated_text="白癜风在治疗后改善。",
        )
        assert len(rows) == 1
        session.commit()

    listing = client.get(
        f"/api/v1/translation-runs/{run_id}/term-candidates?page=1&page_size=40",
        headers=_headers(),
    )
    assert listing.status_code == 200, listing.text
    payload = listing.json()
    assert payload["unresolved"] == 1
    assert payload["rules"]["method"]
    candidate = payload["items"][0]
    assert candidate["source_term"] == "Vitiligo"
    assert candidate["observed_target"] == ""
    assert candidate["occurrence_count"] == 1
    assert candidate["extraction_reason"].startswith("deterministic:")

    blocked = client.post(
        f"/api/v1/translation-runs/{run_id}/review-decision",
        headers=_headers(),
        json={"decision": "approve"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["unresolved_term_count"] == 1

    decided = client.post(
        f"/api/v1/translation-runs/{run_id}/term-candidates/{candidate['id']}/decision",
        headers=_headers(),
        json={
            "action": "approve",
            "expected_version": candidate["version"],
            "target_term": "白癜风",
        },
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["candidate"]["confirmed_target"] == "白癜风"


def test_affiliation_review_edit_creates_superseding_generation(client, monkeypatch):
    from qyunslation.workbench.term_extract import sync_affiliation_segments_from_text

    run_id = _make_run(client, "affiliation-review")
    source = "1 Department of Dermatology, New York Medical College"
    machine = "1 纽约医学院皮肤病学系"
    with persist_db.SessionLocal() as session:
        run = session.get(TranslationRunRecord, run_id)
        preflight = session.get(PreflightRecord, run.preflight_id)
        run.quality_state = "review_ready"
        run.qa_summary = {"blocker": 0, "warning": 0, "info": 0}
        rows = sync_affiliation_segments_from_text(
            session,
            run=run,
            preflight=preflight,
            source_text=source,
            translated_text=machine,
        )
        assert len(rows) == 1
        session.commit()

    listing = client.get(
        f"/api/v1/translation-runs/{run_id}/affiliation-segments", headers=_headers()
    )
    assert listing.status_code == 200, listing.text
    segment = listing.json()["items"][0]
    assert listing.json()["unconfirmed"] == 1
    assert segment["machine_text"] == machine

    revised = "1 纽约医学院皮肤科"
    approved = client.patch(
        f"/api/v1/translation-runs/{run_id}/affiliation-segments/{segment['id']}",
        headers=_headers(),
        json={"expected_version": segment["version"], "revised_text": revised},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["segment"]["status"] == "approved"

    async def fake_launch(*, run, preflight, target_language, session, **_kwargs):
        run.status = "queued"
        run.stage = "validation"

    monkeypatch.setattr("qyunslation.api.v1._launch_translation_run", fake_launch)
    regenerated = client.post(
        f"/api/v1/translation-runs/{run_id}/apply-corrections", headers=_headers()
    )
    assert regenerated.status_code == 201, regenerated.text
    next_run = regenerated.json()
    assert next_run["generation"] == 2
    assert next_run["settings"]["review_overrides"] == {source: revised}

    old = client.get(f"/api/v1/translation-runs/{run_id}", headers=_headers()).json()
    assert old["formal_gate"]["superseding_run_id"] == next_run["id"]


def _make_run(client, key):
    preflight = client.post(
        "/api/v1/preflights",
        headers=_headers(),
        files={"file": ("protocol.pdf", b"%PDF-1.7", "application/pdf")},
    ).json()
    created = client.post(
        "/api/v1/translation-runs",
        headers={**_headers(), "Idempotency-Key": key},
        json={"preflight_id": preflight["id"]},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_auto_qa_emits_qa_and_review_stage_events(client):
    from qyunslation.api.v1 import _maybe_run_auto_qa

    run_id = _make_run(client, "qa-events")
    with persist_db.SessionLocal() as session:
        run = session.scalar(select(TranslationRunRecord).where(TranslationRunRecord.id == run_id))
        run.quality_state = "draft"
        run.stage = "layout"
        _maybe_run_auto_qa(session, run)
        session.commit()
    events = client.get(f"/api/v1/translation-runs/{run_id}/events", headers=_headers()).json()
    items = events["items"]
    stages = {(e["stage"], e["state"]) for e in items}
    assert ("qa", "completed") in stages or ("qa", "blocked") in stages


def test_unapproved_formal_artifact_is_not_previewed_as_formal(client, tmp_path):
    from qyunslation.persist.models import TranslationArtifact

    run_id = _make_run(client, "preview-gate")
    artifact_root = tmp_path / "artifacts"
    with persist_db.SessionLocal() as session:
        run = session.scalar(select(TranslationRunRecord).where(TranslationRunRecord.id == run_id))
        run.quality_state = "review_ready"
        key = f"{run.tenant_id}/{run.id}/formal.pdf"
        target = artifact_root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"%PDF-1.7 formal")
        session.add(
            TranslationArtifact(
                run_id=run.id,
                tenant_id=run.tenant_id,
                artifact_key="formal:pdf",
                kind="formal",
                file_type="pdf",
                filename="formal.pdf",
                media_type="application/pdf",
                storage_key=key,
                size_bytes=target.stat().st_size,
                sha256="0" * 64,
                formal_export=True,
            )
        )
        session.commit()
    resp = client.get(
        f"/api/v1/translation-runs/{run_id}/preview/translated", headers=_headers()
    )
    assert resp.status_code in {404, 409}
    assert b"formal" not in resp.content or resp.status_code != 200
