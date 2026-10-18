"""PLAN-078a: a finished executor is not "translating"; QA service trouble is not a quality verdict."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from _plan078_flow import (
    ADMIN,
    OWNER,
    REVIEWER,
    SwitchableTermProvider,
    UnavailableTermProvider,
    make_client,
    run_to_gate,
)
from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist import db as persist_db
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base, TranslationRunRecord

pytest.importorskip("pymupdf")


def _run(client, run_id, headers=OWNER):
    return client.get(f"/api/v1/translation-runs/{run_id}", headers=headers).json()


# --- a2: gated -------------------------------------------------------------------


def test_untranslated_output_is_gated_with_qa_action(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=False) as client:
        run_id, state = run_to_gate(client, ADMIN, tmp_path, "g-blocked")
        assert state["quality_state"] == "qa_blocked"
        assert state["status"] == "gated"
        assert state["lifecycle"] == "qa_action"
        assert state["progress"] is None
        actions = set(state["allowed_actions"])
        assert {"archive", "delete", "retry", "rename"} <= actions
        assert "cancel" not in actions or "discard" in actions  # never the misleading "cancel"
        assert "resume" not in actions
    reset_engine()


def test_translated_output_is_gated_as_review(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=True) as client:
        run_id, state = run_to_gate(client, OWNER, tmp_path, "g-review")
        assert state["quality_state"] == "review_ready", state["qa_summary"]
        assert state["status"] == "gated"
        assert state["lifecycle"] == "review"
        assert state["next_action"] == "review"
        assert "approve" not in state["allowed_actions"]  # the submitter is not a reviewer
        assert "approve" in _run(client, run_id, ADMIN)["allowed_actions"]
    reset_engine()


def test_gated_run_can_be_archived_restored_and_deleted(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=False) as client:
        run_id, _ = run_to_gate(client, ADMIN, tmp_path, "g-manage")
        base = f"/api/v1/translation-runs/{run_id}"
        assert client.patch(base, headers=ADMIN, json={"archived": True}).status_code == 200
        assert client.post(f"{base}/restore", headers=ADMIN).status_code == 200
        assert client.delete(base, headers=ADMIN).status_code == 204
    reset_engine()


def test_gated_run_is_not_marked_interrupted_by_stale_heartbeat(monkeypatch, tmp_path):
    from qyunslation.api.v1 import reconcile_stale_runs

    with make_client(monkeypatch, tmp_path, translate=False) as client:
        run_id, state = run_to_gate(client, ADMIN, tmp_path, "g-heartbeat")
        assert state["status"] == "gated"
        with persist_db.SessionLocal() as session:
            run = session.get(TranslationRunRecord, run_id)
            run.heartbeat_at = None
            session.commit()
            assert reconcile_stale_runs(session) == 0
            session.commit()
        assert _run(client, run_id, ADMIN)["status"] == "gated"
    reset_engine()


def test_cancel_on_gated_run_means_discard_and_stays_cancelled(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=False) as client:
        run_id, _ = run_to_gate(client, ADMIN, tmp_path, "g-discard")
        cancelled = client.post(f"/api/v1/translation-runs/{run_id}/cancel", headers=ADMIN)
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["quality_state"] == "qa_blocked"  # evidence of why is kept
        assert _run(client, run_id, ADMIN)["status"] == "cancelled"
    reset_engine()


# --- a3: request_changes -----------------------------------------------------------


def test_request_changes_does_not_pretend_to_translate(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=True) as client:
        run_id, state = run_to_gate(client, ADMIN, tmp_path, "g-changes")
        assert state["quality_state"] == "review_ready"
        decided = client.post(
            f"/api/v1/translation-runs/{run_id}/review-decision",
            headers=ADMIN,
            json={"decision": "request_changes", "comment": "术语不一致"},
        )
        assert decided.status_code == 200
        for _ in range(3):  # repeated polling must not change the answer
            body = _run(client, run_id, ADMIN)
            assert body["status"] == "gated"
            assert body["quality_state"] == "changes_requested"
            assert body["lifecycle"] == "changes_requested"
        assert "revise" in body["allowed_actions"] or "retry" in body["allowed_actions"]
        assert "archive" in body["allowed_actions"]
    reset_engine()


# --- a5: QA service trouble is not a quality verdict ------------------------------------


def test_term_model_outage_is_qa_unavailable_not_a_blocker(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=True, provider=UnavailableTermProvider()) as client:
        run_id, state = run_to_gate(client, ADMIN, tmp_path, "g-unavailable")
        assert state["quality_state"] == "qa_unavailable"
        assert state["lifecycle"] == "qa_unavailable"
        assert state["status"] == "gated"
        assert state["qa_summary"]["blocker"] == 0
        assert state["qa_summary"]["unavailable"] >= 1
        assert state["formal_gate"]["passed"] is False
        assert "qa_unavailable" in state["formal_gate"]["reasons"]
        items = client.get(f"/api/v1/translation-runs/{run_id}/qa-items", headers=ADMIN).json()["items"]
        degraded = [i for i in items if i["code"] == "TERM_EXTRACTION_DEGRADED"]
        assert degraded and degraded[0]["severity"] == "unavailable"
        denied = client.post(
            f"/api/v1/translation-runs/{run_id}/review-decision", headers=ADMIN, json={"decision": "approve"}
        )
        assert denied.status_code == 409
    reset_engine()


def test_requalify_with_outage_still_blocks_and_recovers_when_service_returns(monkeypatch, tmp_path):
    provider = SwitchableTermProvider(available=False)
    with make_client(monkeypatch, tmp_path, translate=True, provider=provider) as client:
        run_id, state = run_to_gate(client, ADMIN, tmp_path, "g-requalify")
        assert state["quality_state"] == "qa_unavailable"
        # Still down: the retry must not clear the degraded flag (H4).
        again = client.post(f"/api/v1/translation-runs/{run_id}/requalify", headers=ADMIN)
        assert again.status_code == 200
        assert again.json()["quality_state"] == "qa_unavailable"
        assert again.json()["formal_gate"]["term_extraction_degraded"] is True
        assert again.json()["formal_gate"]["passed"] is False
        # Service restored: the same call now reaches a verdict.
        provider.available = True
        recovered = client.post(f"/api/v1/translation-runs/{run_id}/requalify", headers=ADMIN)
        assert recovered.status_code == 200
        assert recovered.json()["quality_state"] == "review_ready"
        assert recovered.json()["formal_gate"]["term_extraction_degraded"] is False
    reset_engine()


def test_requalify_refused_while_executing(monkeypatch, tmp_path):
    from qyunslation.api import v1 as api_v1_module

    with make_client(monkeypatch, tmp_path, translate=True) as client:
        pf = client.post(
            "/api/v1/preflights",
            headers=ADMIN,
            files={"file": ("p.pdf", b"%PDF-1.7 x", "application/pdf")},
        ).json()

        async def stub_launch(*, run, preflight, target_language, **kwargs):
            run.status = "translating"
            run.stage = "text"

        monkeypatch.setattr(api_v1_module, "_launch_translation_run", stub_launch)
        run_id = client.post(
            "/api/v1/translation-runs",
            headers={**ADMIN, "Idempotency-Key": "g-exec"},
            json={"preflight_id": pf["id"]},
        ).json()["id"]
        assert client.post(f"/api/v1/translation-runs/{run_id}/requalify", headers=ADMIN).status_code == 409
    reset_engine()


# --- a8 / D1: confidential material uses the internal term model -------------------------


def test_confidential_run_reaches_a_verdict_without_external_models(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=True) as client:
        run_id, state = run_to_gate(
            client, ADMIN, tmp_path, "g-conf", document_classification="confidential"
        )
        assert state["quality_state"] == "review_ready", state["qa_summary"]
        assert state["settings"]["term_model_profile_id"] == "term-internal-qwen"
        assert state["formal_gate"]["term_extraction_degraded"] is False
        from qyunslation.persist.models import AuditEvent
        from sqlalchemy import select

        with persist_db.SessionLocal() as session:
            egress = [
                row
                for row in session.scalars(select(AuditEvent).where(AuditEvent.action == "translation_run.egress"))
            ]
            assert egress == []
    reset_engine()


def test_confidential_gets_the_internal_term_profile_and_no_external_one(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=True) as client:
        profiles = client.get("/api/v1/model-profiles?classification=confidential", headers=ADMIN).json()
        items = profiles.get("items") or profiles.get("profiles")
        by_id = {p["profile_id"]: p for p in items}
        assert by_id["term-internal-qwen"]["role"] == "term_suggester"
        assert "term-deepseek-flash" not in by_id  # still never offered for confidential
    reset_engine()
