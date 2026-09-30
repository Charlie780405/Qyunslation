from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base


@pytest.fixture()
def client(monkeypatch, tmp_path: Path):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    monkeypatch.setenv("QYUNSLATION_PREFLIGHT_ROOT", str(tmp_path / "preflights"))
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as current:
        yield current
    reset_engine()


def headers():
    return {"X-Dev-User": "planner", "X-Dev-Tenant": "pilot"}


def test_translation_run_is_durable_and_idempotent_when_runner_is_unavailable(client):
    preflight = client.post(
        "/api/v1/preflights",
        headers=headers(),
        files={"file": ("protocol.txt", b"clinical text", "text/plain")},
    ).json()
    body = {"preflight_id": preflight["id"], "direction": "English → 简体中文", "profile": "临床研究文档"}
    first = client.post(
        "/api/v1/translation-runs",
        headers={**headers(), "Idempotency-Key": "run-once"},
        json=body,
    )
    assert first.status_code == 201
    assert first.json()["status"] == "blocked"
    assert first.json()["degradation_reason"] == "translation runner unavailable"
    second = client.post(
        "/api/v1/translation-runs",
        headers={**headers(), "Idempotency-Key": "run-once"},
        json=body,
    )
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    listing = client.get("/api/v1/translation-runs", headers=headers())
    assert listing.status_code == 200
    assert listing.json()["items"][0]["preflight_id"] == preflight["id"]


def test_retry_allocates_new_generation_without_overwriting_original(client):
    preflight = client.post(
        "/api/v1/preflights",
        headers=headers(),
        files={"file": ("protocol.txt", b"clinical text", "text/plain")},
    ).json()
    created = client.post(
        "/api/v1/translation-runs",
        headers=headers(),
        json={"preflight_id": preflight["id"]},
    ).json()
    retry = client.post(f"/api/v1/translation-runs/{created['id']}/retry", headers=headers())
    assert retry.status_code == 201
    assert retry.json()["generation"] == 2
    assert retry.json()["id"] != created["id"]
    repeated = client.post(f"/api/v1/translation-runs/{created['id']}/retry", headers=headers())
    assert repeated.status_code == 201
    assert repeated.json()["id"] == retry.json()["id"]
    assert len(client.get("/api/v1/translation-runs", headers=headers()).json()["items"]) == 2
