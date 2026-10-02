from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base


@pytest.fixture()
def client(monkeypatch, tmp_path):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    monkeypatch.setenv("QYUNSLATION_PREFLIGHT_ROOT", str(tmp_path / "preflights"))
    monkeypatch.setenv("QYUNSLATION_RUNNER_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("QYUNSLATION_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("QYUNSLATION_AD_PROMPT_TENANTS", "pilot")
    Base.metadata.create_all(init_engine("sqlite+pysqlite:///:memory:"))
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as current:
        yield current
    reset_engine()


def _headers():
    return {"X-Dev-User": "test01@qyunslation.com", "X-Dev-Tenant": "pilot"}


def test_ad_run_exposes_metadata_only_prompt_snapshot(client):
    preflight = client.post(
        "/api/v1/preflights",
        headers=_headers(),
        files={"file": ("ad.txt", b"Patients with atopic dermatitis received dupilumab.", "text/plain")},
    ).json()
    response = client.post(
        "/api/v1/translation-runs",
        headers={**_headers(), "Idempotency-Key": "ad-contract-1"},
        json={
            "preflight_id": preflight["id"],
            "domain_profile": "ad",
            "direction": "English → 简体中文",
            "profile": "医学研究文献",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["domain_profile"] == "ad"
    assert body["prompt_snapshot"]["profile_id"] == "ad.en-zh.literature.translate.v1"
    assert "text" not in body["prompt_snapshot"]
    assert "custom_prompt" not in body["settings"]


def test_ad_run_rejects_missing_domain_evidence(client):
    preflight = client.post(
        "/api/v1/preflights",
        headers=_headers(),
        files={"file": ("general.txt", b"A general archived document.", "text/plain")},
    ).json()
    response = client.post(
        "/api/v1/translation-runs",
        headers={**_headers(), "Idempotency-Key": "ad-contract-2"},
        json={"preflight_id": preflight["id"], "domain_profile": "ad"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "AD_DOMAIN_EVIDENCE_MISSING"


def test_ad_pilot_respects_tenant_allowlist(client, monkeypatch):
    preflight = client.post(
        "/api/v1/preflights",
        headers=_headers(),
        files={"file": ("ad.txt", b"Patients with atopic dermatitis received dupilumab.", "text/plain")},
    ).json()
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    monkeypatch.setenv("QYUNSLATION_AD_PROMPT_MODE", "pilot")
    monkeypatch.setenv("QYUNSLATION_AD_PROMPT_TENANTS", "research")
    response = client.post(
        "/api/v1/translation-runs",
        headers={**_headers(), "Idempotency-Key": "ad-contract-allowlist"},
        json={
            "preflight_id": preflight["id"],
            "domain_profile": "ad",
            "direction": "English → 简体中文",
            "profile": "医学研究文献",
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "AD_ROLLOUT_DENIED"
