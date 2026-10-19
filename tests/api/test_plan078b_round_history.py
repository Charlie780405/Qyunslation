"""PLAN-078b slice 1: items carry identity, a re-check keeps history and reports what changed."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from _plan078_flow import ADMIN, SwitchableTermProvider, make_client, run_to_gate
from qyunslation.api import v1 as api_v1_module
from qyunslation.persist import db as persist_db
from qyunslation.persist.db import reset_engine
from qyunslation.persist.models import QaCheckRound, QaItem, TranslationRunRecord
from qyunslation.pipeline.qa import registry

pytest.importorskip("pymupdf")


def _items(client, run_id, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"/api/v1/translation-runs/{run_id}/qa-items" + (f"?{query}" if query else "")
    return client.get(url, headers=ADMIN).json()


def test_items_carry_identity_class_location_and_guidance(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=False) as client:
        run_id, state = run_to_gate(client, ADMIN, tmp_path, "h-identity")
        payload = _items(client, run_id)
        blockers = [i for i in payload["items"] if i["severity"] == "blocker"]
        assert blockers, payload
        item = next(i for i in blockers if i["code"] == "UNTRANSLATED_BODY")
        assert item["rule_class"] == "C1"
        assert item["title"] and item["why"] and item["how"]
        assert len(item["fingerprint"]) == 64
        assert item["is_current"] is True
        assert "location" in item and isinstance(item["location"], dict)
        assert item["round_id"]
        with persist_db.SessionLocal() as session:
            row = session.scalar(select(QaCheckRound))
            assert row.rule_set_version == registry.rule_set_version()
            assert row.artifact_digest and len(row.artifact_digest) == 64
            stored = session.get(QaItem, item["id"])
            assert stored.evidence_json["rule_version"] == registry.rule_set_version()
    reset_engine()


def test_rules_endpoint_publishes_the_registry(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=False) as client:
        rules = client.get("/api/v1/qa-rules", headers=ADMIN).json()
        by_code = {r["code"]: r for r in rules["items"]}
        assert rules["rule_set_version"] == registry.rule_set_version()
        assert by_code["AD_NUMBER_DRIFT"]["rule_class"] == "C1"
        assert by_code["AD_NUMBER_DRIFT"]["batchable"] is False
        assert by_code["LITERAL_MISSING_DOSE"]["batchable"] is False
        assert "title" in by_code["LOGO_MISSING"]
    reset_engine()


def test_recheck_keeps_history_and_reports_what_changed(monkeypatch, tmp_path):
    provider = SwitchableTermProvider(available=False)
    with make_client(monkeypatch, tmp_path, translate=True, provider=provider) as client:
        run_id, state = run_to_gate(client, ADMIN, tmp_path, "h-history")
        assert state["quality_state"] == "qa_unavailable"
        first = _items(client, run_id)
        assert [i["code"] for i in first["items"] if i["severity"] == "unavailable"] == ["TERM_EXTRACTION_DEGRADED"]

        provider.available = True
        client.post(f"/api/v1/translation-runs/{run_id}/requalify", headers=ADMIN)
        after = _items(client, run_id)
        assert "TERM_EXTRACTION_DEGRADED" not in {i["code"] for i in after["items"]}
        assert all(i["is_current"] for i in after["items"])

        everything = _items(client, run_id, include_history="true")
        old = [i for i in everything["items"] if not i["is_current"]]
        assert any(i["code"] == "TERM_EXTRACTION_DEGRADED" for i in old)  # not erased

        with persist_db.SessionLocal() as session:
            rounds = list(session.scalars(select(QaCheckRound).order_by(QaCheckRound.round_no)))
            assert [r.round_no for r in rounds] == [1, 2]
            diff = rounds[1].diff_json
            assert diff["resolved"] == 1 and diff["new"] == 0
            assert diff["resolved_items"][0]["code"] == "TERM_EXTRACTION_DEGRADED"
        assert after["check"]["round_no"] == 2
        assert after["check"]["diff"]["resolved"] == 1
    reset_engine()


def test_unchanged_output_reports_persisting_problems(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=False) as client:
        run_id, state = run_to_gate(client, ADMIN, tmp_path, "h-persist")
        before = {i["fingerprint"] for i in _items(client, run_id)["items"] if i["severity"] == "blocker"}
        assert before
        client.post(f"/api/v1/translation-runs/{run_id}/requalify", headers=ADMIN)
        payload = _items(client, run_id)
        after = {i["fingerprint"] for i in payload["items"] if i["severity"] == "blocker"}
        assert after == before  # the same problems are recognised as the same problems
        diff = payload["check"]["diff"]
        assert diff["new"] == 0 and diff["resolved"] == 0 and diff["persisting"] >= len(before)
    reset_engine()


def test_check_for_output_that_changed_meanwhile_is_discarded(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=True) as client:
        run_id, state = run_to_gate(client, ADMIN, tmp_path, "h-stale")
        assert state["quality_state"] == "review_ready"
        calls = {"n": 0}
        real = api_v1_module._artifact_digest

        def changing(*args, **kwargs):
            calls["n"] += 1
            return real(*args, **kwargs) if calls["n"] % 2 else "f" * 64  # differs at the end of the pass

        monkeypatch.setattr(api_v1_module, "_artifact_digest", changing)
        before = {i["id"] for i in _items(client, run_id)["items"]}
        client.post(f"/api/v1/translation-runs/{run_id}/requalify", headers=ADMIN)
        with persist_db.SessionLocal() as session:
            last = session.scalar(select(QaCheckRound).order_by(QaCheckRound.round_no.desc()))
            assert last.status == "failed" and last.error_code == "output_changed"
        assert {i["id"] for i in _items(client, run_id)["items"]} == before  # old verdict untouched
    reset_engine()


def test_old_items_without_identity_are_completed_on_read(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=False) as client:
        run_id, _ = run_to_gate(client, ADMIN, tmp_path, "h-legacy")
        with persist_db.SessionLocal() as session:
            run = session.get(TranslationRunRecord, run_id)
            for item in session.scalars(select(QaItem).where(QaItem.run_id == run_id)):
                item.fingerprint = item.rule_class = item.round_id = item.location_json = None
            session.commit()
        items = _items(client, run_id)["items"]
        assert all(i["fingerprint"] and i["rule_class"] for i in items)
        assert all(isinstance(i["location"], dict) for i in items)
    reset_engine()


def test_resume_keeps_the_old_verdict_as_history(monkeypatch, tmp_path):
    with make_client(monkeypatch, tmp_path, translate=False) as client:
        run_id, _ = run_to_gate(client, ADMIN, tmp_path, "h-resume")
        with persist_db.SessionLocal() as session:
            session.get(TranslationRunRecord, run_id).status = "interrupted"
            session.commit()

        async def stub_launch(*, run, preflight, target_language, **kwargs):
            run.status = "translating"

        monkeypatch.setattr(api_v1_module, "_launch_translation_run", stub_launch)
        assert client.post(f"/api/v1/translation-runs/{run_id}/resume", headers=ADMIN).status_code == 200
        assert _items(client, run_id)["items"] == []
        assert _items(client, run_id, include_history="true")["items"]  # history survives
    reset_engine()
