"""PLAN-078b slice 4: fixing a problem means a new, frozen-config version that is checked against the last."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from _plan078_flow import ADMIN, OWNER, make_client, run_to_gate, write_cli
from qyunslation.api import v1 as api_v1_module
from qyunslation.persist import db as persist_db
from qyunslation.persist.db import reset_engine
from qyunslation.persist.models import PreflightRecord, QaDisposition, QaItem, TranslationRunRecord
from qyunslation.pipeline.qa import QaFinding

pytest.importorskip("pymupdf")


def _poll(client, run_id, headers=ADMIN, seconds=20):
    body = {}
    deadline = time.time() + seconds
    while time.time() < deadline:
        body = client.get(f"/api/v1/translation-runs/{run_id}", headers=headers).json()
        if body.get("status") == "gated" and body.get("quality_state") != "draft":
            return body
        time.sleep(0.05)
    return body


def _revise(client, run_id, headers=ADMIN, **body):
    return client.post(f"/api/v1/translation-runs/{run_id}/revisions", headers=headers, json=body)


def test_revision_is_a_new_version_checked_against_the_previous_one(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=False) as client:
        run_id, state = run_to_gate(client, OWNER, tmp_path, "rev-1")
        assert state["quality_state"] == "qa_blocked"
        assert "revise" in state["allowed_actions"]

        write_cli(tmp_path / "cli", translate=True)  # the cause was fixed
        created = _revise(client, run_id)
        assert created.status_code == 201, created.text
        new = created.json()
        assert new["id"] != run_id and new["generation"] == 2
        assert new["settings"]["revision_of"] == {"run_id": run_id, "generation": 1}
        assert new["quality_state"] in {"draft"} and new["lifecycle"] in {"executing", "qa_checking"}

        old = client.get(f"/api/v1/translation-runs/{run_id}", headers=ADMIN).json()
        assert old["superseded_by"] == new["id"]
        assert "approve" not in old["allowed_actions"]  # the old version is frozen

        final = _poll(client, new["id"])
        assert final["quality_state"] == "review_ready", final["qa_summary"]
        diff = final["qa_check"]["diff"]
        assert diff["baseline"] == "previous_version"
        assert diff["new"] == 0 and diff["resolved"] >= 1
        assert any(item["code"] == "UNTRANSLATED_BODY" for item in diff["resolved_items"])

        again = _revise(client, run_id)  # a second click returns the same new version
        assert again.json()["id"] == new["id"]
    reset_engine()


def test_revision_works_after_the_pre_check_window_has_passed(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=False) as client:
        run_id, _ = run_to_gate(client, OWNER, tmp_path, "rev-expired")
        with persist_db.SessionLocal() as session:
            run = session.get(TranslationRunRecord, run_id)
            preflight = session.get(PreflightRecord, run.preflight_id)
            preflight.expires_at = datetime.now(timezone.utc) - timedelta(days=2)  # long past the 24h window
            session.commit()
        write_cli(tmp_path / "cli", translate=True)
        created = _revise(client, run_id)
        assert created.status_code == 201, created.text
        with persist_db.SessionLocal() as session:
            preflight = session.scalar(select(PreflightRecord))
            expires = preflight.expires_at.replace(tzinfo=timezone.utc) if preflight.expires_at.tzinfo is None else preflight.expires_at
            assert expires > datetime.now(timezone.utc)  # re-armed because a task still uses it
    reset_engine()


def test_revision_explains_when_the_source_file_is_gone(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=False) as client:
        run_id, _ = run_to_gate(client, OWNER, tmp_path, "rev-gone")
        with persist_db.SessionLocal() as session:
            run = session.get(TranslationRunRecord, run_id)
            preflight = session.get(PreflightRecord, run.preflight_id)
            api_v1_module._preflight_path(preflight).unlink()
            preflight.expires_at = datetime.now(timezone.utc) - timedelta(days=2)
            session.commit()
        response = _revise(client, run_id)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "SOURCE_UNAVAILABLE"
    reset_engine()


def test_retry_also_survives_an_expired_pre_check_and_records_its_origin(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=False) as client:
        run_id, _ = run_to_gate(client, OWNER, tmp_path, "rev-retry")
        with persist_db.SessionLocal() as session:
            run = session.get(TranslationRunRecord, run_id)
            session.get(PreflightRecord, run.preflight_id).expires_at = datetime.now(timezone.utc) - timedelta(days=2)
            session.commit()
        retried = client.post(f"/api/v1/translation-runs/{run_id}/retry", headers=ADMIN, json={})
        assert retried.status_code == 201, retried.text
        assert retried.json()["settings"]["revision_of"]["run_id"] == run_id
    reset_engine()


def test_a_previous_versions_exception_is_pointed_out_but_not_inherited(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=True) as client:
        run_id, _ = run_to_gate(client, OWNER, tmp_path, "rev-prior")
        spec = ("blocker", "LOGO_MISSING", {"output_kind": "mono"})

        def inject(target_run_id):
            with persist_db.SessionLocal() as session:
                run = session.get(TranslationRunRecord, target_run_id)
                for old in session.scalars(select(QaItem).where(QaItem.run_id == target_run_id)):
                    old.is_current = False
                item = api_v1_module._new_qa_item(
                    run, QaFinding(category="x", severity=spec[0], code=spec[1], message="m", evidence=spec[2]),
                    round_id=None, trigger="test",
                )
                session.add(item)
                run.quality_state = "qa_blocked"
                run.qa_summary = {"blocker": 1}
                session.commit()
                return item.id

        first_item = inject(run_id)
        waived = client.post(
            f"/api/v1/translation-runs/{run_id}/qa-items/{first_item}/dispositions",
            headers=ADMIN, json={"action": "grant_waiver", "reason": "首页印章在译文中位置不同，已核对"},
        )
        assert waived.status_code == 200, waived.text

        created = _revise(client, run_id).json()
        new_id = created["id"]
        _poll(client, new_id)
        second_item = inject(new_id)
        with persist_db.SessionLocal() as session:
            session.get(TranslationRunRecord, new_id).status = "gated"
            session.commit()
        items = client.get(f"/api/v1/translation-runs/{new_id}/qa-items", headers=ADMIN).json()["items"]
        logo = next(i for i in items if i["id"] == second_item)
        assert logo["status"] == "open"  # not inherited ...
        assert logo["prior_version_disposition"]["action"] == "grant_waiver"  # ... but the reviewer is told
    reset_engine()
