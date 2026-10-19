"""PLAN-078c: the configuration a person confirms is the configuration that runs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from qyunslation.api import v1 as api_v1_module
from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist import db as persist_db
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base, PreflightRecord, TranslationRunRecord

OWNER = {"X-Dev-User": "owner1", "X-Dev-Tenant": "pilot", "X-Dev-Role": "translator"}
OTHER = {"X-Dev-User": "other1", "X-Dev-Tenant": "pilot", "X-Dev-Role": "translator"}


@pytest.fixture()
def client(monkeypatch, tmp_path: Path):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    monkeypatch.delenv("QYUNSLATION_DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("QYUNSLATION_PREFLIGHT_ROOT", str(tmp_path / "preflights"))
    monkeypatch.setenv("QYUNSLATION_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("QYUNSLATION_RUNNER_ROOT", str(tmp_path / "runs"))
    Base.metadata.create_all(init_engine("sqlite+pysqlite:///:memory:"))

    async def stub_launch(*, run, preflight, target_language, **kwargs):
        run.status = "failed"
        run.stage = "qa"

    monkeypatch.setattr(api_v1_module, "_launch_translation_run", stub_launch)
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as current:
        yield current
    reset_engine()


def _preflight(client, headers=OWNER, name="doc.pdf", data=b"%PDF-1.7 a"):
    mime = "application/pdf" if name.endswith(".pdf") else "text/plain"
    response = client.post("/api/v1/preflights", headers=headers, files={"file": (name, data, mime)})
    assert response.status_code == 201, response.text
    return response.json()


def _validate(client, preflight_id, headers=OWNER, **body):
    return client.post(
        "/api/v1/translation-runs/validate", headers=headers, json={"preflight_id": preflight_id, **body}
    )


def _create(client, preflight_id, key, headers=OWNER, **body):
    return client.post(
        "/api/v1/translation-runs",
        headers={**headers, "Idempotency-Key": key},
        json={"preflight_id": preflight_id, **body},
    )


def _codes(payload, kind="errors"):
    return {item["code"] for item in payload[kind]}


# --- validate: what will actually run -----------------------------------------------------------


def test_validate_returns_the_resolved_configuration_and_a_digest(client):
    pf = _preflight(client)
    response = _validate(client, pf["id"], profile="监管申报材料")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True and body["errors"] == []
    config = body["config"]
    assert config["direction"] == "English → 简体中文"
    assert config["profile"] == "监管申报材料"
    assert config["document_classification"] == "internal"
    assert config["model_profile_id"] == "internal-qwen-quality"
    assert config["term_model_profile_id"] == "term-internal-qwen"  # D1: resolved, not left implicit
    assert config["egress_scope"] == "none"
    assert config["model"]["label"] and config["term_model"]["label"]
    assert config["bilingual_effective"] is True  # PDF can produce the pair
    assert len(body["config_digest"]) == 64
    assert body["preflight"]["id"] == pf["id"]


def test_validate_digest_is_the_digest_the_run_is_created_with(client):
    pf = _preflight(client)
    digest = _validate(client, pf["id"], bilingual=False).json()["config_digest"]
    created = _create(client, pf["id"], "k-digest", bilingual=False, config_digest=digest)
    assert created.status_code == 201, created.text
    assert created.json()["settings"]["config_digest"] == digest
    assert created.json()["settings"]["config_digest_v"] == 2


def test_digest_changes_with_every_setting_that_matters(client):
    pf = _preflight(client)
    base = _validate(client, pf["id"]).json()["config_digest"]
    assert _validate(client, pf["id"]).json()["config_digest"] == base  # deterministic
    for change in (
        {"bilingual": False},
        {"profile": "通用医药文档"},
        {"document_classification": "confidential"},
        {"document_classification": "public"},
        {"source_language": "简体中文", "target_language": "English"},
    ):
        assert _validate(client, pf["id"], **change).json()["config_digest"] != base, change
    # a rename is not a configuration change
    assert _validate(client, pf["id"], display_name="新名字").json()["config_digest"] == base


def test_digest_follows_the_term_model_that_will_really_be_used(client, monkeypatch):
    pf = _preflight(client)
    before = _validate(client, pf["id"]).json()
    monkeypatch.setenv("QYUNSLATION_DEEPSEEK_API_KEY", "test-key")  # default term model flips to DeepSeek
    after = _validate(client, pf["id"]).json()
    assert before["config"]["term_model_profile_id"] == "term-internal-qwen"
    assert after["config"]["term_model_profile_id"] == "term-deepseek-flash"
    assert after["config_digest"] != before["config_digest"]
    assert after["config"]["egress_scope"] == "redacted_term_snippets"
    assert "EGRESS_REDACTED_TERMS" in _codes(after, "warnings")


def test_validate_reports_every_problem_at_once(client):
    pf = _preflight(client)
    body = _validate(
        client, pf["id"], source_language="English", target_language="English", model_profile_id="no-such-model"
    ).json()
    assert body["ok"] is False
    assert {"LANGUAGE_SAME", "MODEL_NOT_ALLOWED"} <= _codes(body)
    assert all(item["message"] for item in body["errors"])
    assert {item["field"] for item in body["errors"]} >= {"language", "model_profile_id"}


@pytest.mark.parametrize(
    "extra,code",
    [
        ({"document_classification": "confidential", "model_profile_id": "public-deepseek-flash"}, "MODEL_NOT_ALLOWED"),
        ({"document_classification": "public", "model_profile_id": "public-deepseek-flash"}, "MODEL_NOT_CONFIGURED"),
        ({"document_classification": "confidential", "term_model_profile_id": "term-deepseek-flash"}, "TERM_MODEL_NOT_ALLOWED"),
        ({"document_classification": "secret"}, "CLASSIFICATION_INVALID"),
        ({"domain_profile": "oncology"}, "DOMAIN_UNSUPPORTED"),
    ],
)
def test_validate_explains_each_kind_of_conflict(client, extra, code):
    pf = _preflight(client)
    body = _validate(client, pf["id"], **extra).json()
    assert body["ok"] is False and code in _codes(body), body["errors"]


def test_validate_warns_when_the_pair_output_is_not_available_for_the_format(client):
    pf = _preflight(client, name="notes.txt", data=b"hello world")
    body = _validate(client, pf["id"], bilingual=True).json()
    assert body["ok"] is True
    assert "BILINGUAL_NOT_SUPPORTED" in _codes(body, "warnings")
    assert body["config"]["bilingual_effective"] is False


def test_validate_does_not_reveal_other_peoples_files(client):
    pf = _preflight(client)
    assert _validate(client, pf["id"], headers=OTHER).status_code == 404
    assert _validate(client, "no-such-id").status_code == 404


def test_validate_flags_a_source_that_already_has_a_task_and_offers_a_copy(client):
    pf = _preflight(client)
    assert _create(client, pf["id"], "used-1").status_code == 201
    body = _validate(client, pf["id"], document_classification="confidential").json()
    assert body["ok"] is False
    error = next(e for e in body["errors"] if e["code"] == "PREFLIGHT_ALREADY_RUN")
    assert error["run_id"] and error["can_copy"] is True
    assert body["preflight"]["used_by_run_id"] == error["run_id"]


def test_validate_flags_an_expired_pre_check(client):
    pf = _preflight(client)
    with persist_db.SessionLocal() as session:
        session.get(PreflightRecord, pf["id"]).expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        session.commit()
    body = _validate(client, pf["id"]).json()
    assert body["ok"] is False and "PREFLIGHT_EXPIRED" in _codes(body)


# --- create: the confirmed digest must still be true -------------------------------------------------


def test_create_rejects_a_stale_confirmation(client):
    pf = _preflight(client)
    digest = _validate(client, pf["id"]).json()["config_digest"]
    changed = _create(client, pf["id"], "stale-1", document_classification="confidential", config_digest=digest)
    assert changed.status_code == 409
    detail = changed.json()["detail"]
    assert detail["code"] == "CONFIG_STALE" and detail["current_digest"] != digest
    assert client.get("/api/v1/translation-runs", headers=OWNER).json()["items"] == []  # nothing was created


def test_create_without_a_digest_still_works(client):
    pf = _preflight(client)
    assert _create(client, pf["id"], "nodigest").status_code == 201


def test_replaying_a_confirmed_request_returns_the_same_run(client):
    pf = _preflight(client)
    digest = _validate(client, pf["id"]).json()["config_digest"]
    first = _create(client, pf["id"], "replay", config_digest=digest).json()
    again = _create(client, pf["id"], "replay", config_digest=digest)
    assert again.status_code == 201 and again.json()["id"] == first["id"]


# --- source files: a task's source is reusable, and changing config never needs a loop ---------------


def test_reuploading_a_used_file_gives_a_fresh_pre_check(client):
    first = _preflight(client)
    assert _create(client, first["id"], "run-a").status_code == 201
    again = _preflight(client)  # the same bytes
    assert again["id"] != first["id"] and again.get("reused") is not True
    created = _create(client, again["id"], "run-b", document_classification="confidential")
    assert created.status_code == 201, created.text


def test_copying_a_pre_check_keeps_the_original_task_intact(client):
    first = _preflight(client)
    run_a = _create(client, first["id"], "copy-a").json()
    copied = client.post(f"/api/v1/preflights/{first['id']}/copy", headers=OWNER)
    assert copied.status_code == 201, copied.text
    new = copied.json()
    assert new["id"] != first["id"] and new["state"] == "ready" and new["filename"] == first["filename"]
    assert new["sha256"] == first["sha256"]
    run_b = _create(client, new["id"], "copy-b", document_classification="confidential")
    assert run_b.status_code == 201 and run_b.json()["id"] != run_a["id"]
    assert client.get(f"/api/v1/translation-runs/{run_a['id']}", headers=OWNER).status_code == 200
    assert client.get(f"/api/v1/preflights/{first['id']}", headers=OWNER).status_code == 200


def test_copying_someone_elses_pre_check_is_refused(client):
    first = _preflight(client)
    assert client.post(f"/api/v1/preflights/{first['id']}/copy", headers=OTHER).status_code == 404


def test_pre_check_list_marks_used_ones_and_restores_only_a_usable_latest(client):
    old = _preflight(client, name="old.pdf", data=b"%PDF-1.7 old")
    run = _create(client, old["id"], "list-a").json()
    new = _preflight(client, name="new.pdf", data=b"%PDF-1.7 new")
    listing = client.get("/api/v1/preflights", headers=OWNER).json()
    by_id = {item["id"]: item for item in listing["items"]}
    assert by_id[old["id"]]["used_by_run_id"] == run["id"]
    assert by_id[new["id"]]["used_by_run_id"] is None
    assert listing["latest"]["id"] == new["id"]
    _create(client, new["id"], "list-b")
    after = client.get("/api/v1/preflights", headers=OWNER).json()
    assert after["latest"] is None  # nothing left that can start a new translation


# --- revisions with changed parameters ------------------------------------------------------------------


def _finished_run(client, key="rev-base", **body):
    pf = _preflight(client, name=f"{key}.pdf", data=f"%PDF-1.7 {key}".encode())
    return _create(client, pf["id"], key, **body).json()


def test_revision_can_change_the_model_class_and_output_mode_and_records_it(client):
    run = _finished_run(client)
    response = client.post(
        f"/api/v1/translation-runs/{run['id']}/revisions",
        headers=OWNER,
        json={"overrides": {"document_classification": "confidential", "bilingual": False}},
    )
    assert response.status_code == 201, response.text
    new = response.json()
    assert new["generation"] == 2
    assert new["document_classification"] == "confidential"
    assert new["settings"]["bilingual"] is False and new["settings"]["bilingual_effective"] is False
    assert new["settings"]["model_snapshot"]["document_classification"] == "confidential"
    assert new["settings"]["config_digest"] != run["settings"]["config_digest"]
    assert new["settings"]["revision_overrides"] == ["bilingual", "document_classification"]
    assert new["settings"]["revision_of"]["run_id"] == run["id"]
    old = client.get(f"/api/v1/translation-runs/{run['id']}", headers=OWNER).json()
    assert old["document_classification"] == "internal"  # the frozen original is untouched


@pytest.mark.parametrize(
    "overrides,status",
    [
        ({"source_language": "简体中文"}, 422),
        ({"domain_profile": "ad"}, 422),
        ({"document_classification": "confidential", "model_profile_id": "public-deepseek-flash"}, 400),
        ({"document_classification": "secret"}, 400),
    ],
)
def test_revision_refuses_overrides_it_cannot_apply_safely(client, overrides, status):
    run = _finished_run(client, key="rev-bad")
    response = client.post(
        f"/api/v1/translation-runs/{run['id']}/revisions", headers=OWNER, json={"overrides": overrides}
    )
    assert response.status_code == status, response.text


def test_revision_without_overrides_keeps_the_frozen_configuration(client):
    run = _finished_run(client, key="rev-same", bilingual=False)
    new = client.post(f"/api/v1/translation-runs/{run['id']}/revisions", headers=OWNER, json={}).json()
    assert new["settings"]["bilingual"] is False
    assert new["settings"]["config_digest"] == run["settings"]["config_digest"]
    assert "revision_overrides" not in new["settings"]
