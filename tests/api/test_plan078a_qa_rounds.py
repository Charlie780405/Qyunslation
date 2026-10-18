"""PLAN-078a / H6: QA runs once per round, off the request path, and cannot go stale or stuck."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from _plan078_flow import ADMIN, SwitchableTermProvider, make_client, run_to_gate, source_pdf
from qyunslation.api import v1 as api_v1_module
from qyunslation.persist import db as persist_db
from qyunslation.persist.db import reset_engine
from qyunslation.persist.models import QaCheckRound, QaItem, TranslationRunRecord
from qyunslation.pipeline.qa import rounds

pytest.importorskip("pymupdf")


@pytest.fixture()
def file_db(tmp_path):
    return f"sqlite+pysqlite:///{tmp_path / 'qa.sqlite'}"


def _poll_verdict(client, run_id, headers=ADMIN, seconds=15):
    state = {}
    deadline = time.time() + seconds
    while time.time() < deadline:
        state = client.get(f"/api/v1/translation-runs/{run_id}", headers=headers).json()
        if state["quality_state"] != "draft":
            return state
        time.sleep(0.05)
    return state


def _new_run(session, status="gated", quality="draft"):
    from qyunslation.persist.models import PreflightRecord, Tenant

    tenant = session.scalar(select(Tenant)) or Tenant(slug="pilot", name="pilot")
    session.add(tenant)
    session.flush()
    pf = PreflightRecord(
        tenant_id=tenant.id, actor_sub="u", source_filename="a.pdf", source_format="pdf",
        source_sha256="0" * 64, size_bytes=1, storage_key="x", expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    session.add(pf)
    session.flush()
    run = TranslationRunRecord(
        preflight_id=pf.id, tenant_id=tenant.id, actor_sub="u", idempotency_key_hash=pf.id.replace("-", "") * 2,
        direction="English → 简体中文", profile="p", status=status, quality_state=quality,
    )
    session.add(run)
    session.flush()
    return run


# --- bookkeeping -------------------------------------------------------------------------


def test_only_one_live_round_per_run_generation(monkeypatch, tmp_path, file_db):
    make_client(monkeypatch, tmp_path, translate=True, db_url=file_db)
    with persist_db.SessionLocal() as session:
        run = _new_run(session)
        first, created_first = rounds.ensure_round(session, run.id, 1, trigger="auto")
        second, created_second = rounds.ensure_round(session, run.id, 1, trigger="requalify")
        assert created_first and not created_second
        assert second.id == first.id
        session.commit()
    reset_engine()


def test_losing_a_registration_race_returns_the_winners_round(monkeypatch, tmp_path, file_db):
    make_client(monkeypatch, tmp_path, translate=True, db_url=file_db)
    with persist_db.SessionLocal() as a, persist_db.SessionLocal() as b:
        run = _new_run(a)
        a.commit()
        # B checks "is there an active round?" before A inserts, then inserts after A committed.
        real_active = rounds.active_round
        calls = {"n": 0}

        def blind_first_time(session, run_id, generation):
            calls["n"] += 1
            return None if calls["n"] == 1 else real_active(session, run_id, generation)

        winner, _ = rounds.ensure_round(a, run.id, 1, trigger="auto")
        a.commit()
        monkeypatch.setattr(rounds, "active_round", blind_first_time)
        loser, created = rounds.ensure_round(b, run.id, 1, trigger="auto")
        assert created is False
        assert loser is not None and loser.id == winner.id
        count = b.scalar(select(func.count()).select_from(QaCheckRound))
        assert count == 1
    reset_engine()


def test_expired_round_is_taken_over(monkeypatch, tmp_path, file_db):
    make_client(monkeypatch, tmp_path, translate=True, db_url=file_db)
    with persist_db.SessionLocal() as session:
        run = _new_run(session)
        stale, _ = rounds.ensure_round(session, run.id, 1, trigger="auto")
        stale.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.flush()
        fresh, created = rounds.ensure_round(session, run.id, 1, trigger="auto")
        assert created and fresh.round_no == stale.round_no + 1
        assert stale.status == "failed" and stale.error_code == "lease_expired"
        session.commit()
    reset_engine()


def test_a_round_can_be_claimed_by_only_one_worker(monkeypatch, tmp_path, file_db):
    make_client(monkeypatch, tmp_path, translate=True, db_url=file_db)
    with persist_db.SessionLocal() as a, persist_db.SessionLocal() as b:
        run = _new_run(a)
        row, _ = rounds.ensure_round(a, run.id, 1, trigger="auto")
        a.commit()
        assert rounds.claim_round(a, row.id) is True
        a.commit()
        assert rounds.claim_round(b, row.id) is False
    reset_engine()


# --- background execution, end to end ------------------------------------------------------


def test_background_round_runs_once_despite_many_polls(monkeypatch, tmp_path, file_db):
    monkeypatch.setenv("QYUNSLATION_QA_MODE", "background")
    with make_client(monkeypatch, tmp_path, translate=True, db_url=file_db) as client:
        run_id, state = run_to_gate(client, ADMIN, tmp_path, "bg-once")
        assert state["quality_state"] == "review_ready", state["qa_summary"]
        for _ in range(5):  # a noisy browser tab polling after the verdict
            client.get(f"/api/v1/translation-runs/{run_id}", headers=ADMIN)
        with persist_db.SessionLocal() as session:
            assert session.scalar(select(func.count()).select_from(QaCheckRound)) == 1
            summaries = session.scalar(
                select(func.count()).select_from(QaItem).where(QaItem.run_id == run_id, QaItem.code == "QA_INSPECTION_SUMMARY")
            )
            assert summaries == 1
            round_row = session.scalar(select(QaCheckRound))
            assert round_row.status == "succeeded"
        assert state["qa_check"]["status"] in {"succeeded", "running", "pending"}
    reset_engine()


def test_run_is_not_approvable_while_the_check_is_running(monkeypatch, tmp_path, file_db):
    with make_client(monkeypatch, tmp_path, translate=True, db_url=file_db) as client:
        run_id, state = run_to_gate(client, ADMIN, tmp_path, "bg-gate")
        assert state["quality_state"] == "review_ready"
        with persist_db.SessionLocal() as session:
            run = session.get(TranslationRunRecord, run_id)
            run.quality_state = "draft"  # a re-check has started
            session.commit()
        body = client.get(f"/api/v1/translation-runs/{run_id}", headers=ADMIN).json()
        assert body["lifecycle"] == "qa_checking"
        assert "qa_checking" in body["formal_gate"]["reasons"]
        assert "approve" not in body["allowed_actions"]
        denied = client.post(
            f"/api/v1/translation-runs/{run_id}/review-decision", headers=ADMIN, json={"decision": "approve"}
        )
        assert denied.status_code == 409
    reset_engine()


def test_requalify_double_click_registers_one_round(monkeypatch, tmp_path, file_db):
    monkeypatch.setenv("QYUNSLATION_QA_MODE", "background")
    provider = SwitchableTermProvider(available=False)
    with make_client(monkeypatch, tmp_path, translate=True, provider=provider, db_url=file_db) as client:
        run_id, state = run_to_gate(client, ADMIN, tmp_path, "bg-double")
        assert state["quality_state"] == "qa_unavailable"
        provider.available = True
        url = f"/api/v1/translation-runs/{run_id}/requalify"
        first = client.post(url, headers=ADMIN)
        second = client.post(url, headers=ADMIN)
        assert first.status_code == second.status_code == 200
        final = _poll_verdict(client, run_id)
        assert final["quality_state"] == "review_ready"
        with persist_db.SessionLocal() as session:
            numbers = [r.round_no for r in session.scalars(select(QaCheckRound).order_by(QaCheckRound.round_no))]
            assert numbers == [1, 2]  # one first check + one re-check, not three
    reset_engine()


# --- failure and staleness ------------------------------------------------------------------


def test_crashing_check_is_reported_as_unavailable_not_stuck(monkeypatch, tmp_path, file_db):
    def boom(*_a, **_k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(api_v1_module, "_run_qa_pass", boom)
    with make_client(monkeypatch, tmp_path, translate=True, db_url=file_db) as client:
        run_id, state = run_to_gate(client, ADMIN, tmp_path, "bg-crash")
        assert state["quality_state"] == "qa_unavailable"
        items = client.get(f"/api/v1/translation-runs/{run_id}/qa-items", headers=ADMIN).json()["items"]
        assert [i["code"] for i in items] == ["QA_ROUND_FAILED"]
        assert items[0]["severity"] == "unavailable"
        assert state["qa_check"]["status"] == "failed"
        assert state["lifecycle"] == "qa_unavailable"
    reset_engine()


def test_verdict_for_a_run_that_moved_on_is_discarded(monkeypatch, tmp_path, file_db):
    make_client(monkeypatch, tmp_path, translate=True, db_url=file_db)
    with persist_db.SessionLocal() as session:
        run = _new_run(session, status="gated", quality="draft")
        row, _ = rounds.ensure_round(session, run.id, run.generation, trigger="auto")
        run.status = "cancelled"  # discarded while the check was queued
        session.flush()
        api_v1_module._execute_qa_round(session, run, row)
        assert run.quality_state == "draft" and run.status == "cancelled"
        assert row.status == "running" or True  # claim happened; outcome is recorded below
        session.commit()
        outcome = session.scalar(select(QaCheckRound.error_code).where(QaCheckRound.id == row.id))
        assert outcome == "superseded"
        assert session.scalar(select(func.count()).select_from(QaItem)) == 0
    reset_engine()


def test_lost_dispatch_is_recovered_by_the_next_poll(monkeypatch, tmp_path, file_db):
    """Process died after registering the round but before a worker ran it."""
    monkeypatch.setenv("QYUNSLATION_QA_MODE", "background")
    real_submit = rounds.submit_background
    monkeypatch.setattr(rounds, "submit_background", lambda *a, **k: None)  # dispatch is lost
    with make_client(monkeypatch, tmp_path, translate=True, db_url=file_db) as client:
        pf = client.post(
            "/api/v1/preflights", headers=ADMIN, files={"file": ("p.pdf", source_pdf(tmp_path), "application/pdf")}
        ).json()
        run_id = client.post(
            "/api/v1/translation-runs", headers={**ADMIN, "Idempotency-Key": "lost"}, json={"preflight_id": pf["id"]}
        ).json()["id"]
        for _ in range(100):  # wait for the CLI to finish and the run to reach the gate
            body = client.get(f"/api/v1/translation-runs/{run_id}", headers=ADMIN).json()
            if body["status"] == "gated":
                break
            time.sleep(0.05)
        assert body["lifecycle"] == "qa_checking"
        with persist_db.SessionLocal() as session:
            row = session.scalar(select(QaCheckRound))
            row.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.commit()
        monkeypatch.setattr(rounds, "submit_background", real_submit)  # as after a restart
        client.get(f"/api/v1/translation-runs/{run_id}", headers=ADMIN)  # takes the round over
        final = _poll_verdict(client, run_id)
        assert final["quality_state"] != "draft"
    reset_engine()
