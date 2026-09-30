# SPDX-License-Identifier: MPL-2.0
"""PLAN-034h：SaaS API 烟囱（health / projects / review enqueue）。"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base


@pytest.fixture()
def client(monkeypatch):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as c:
        yield c
    reset_engine()


@pytest.fixture()
def no_bypass_client(monkeypatch):
    """无 Dev 旁路、未配 OIDC：等价生产下的匿名访问者。"""
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.delenv("QYUNSLATION_DEV_AUTH_BYPASS", raising=False)
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as c:
        yield c
    reset_engine()


def test_health_hides_config_from_anonymous(no_bypass_client):
    """匿名只应看到 schema/db，不应看到 env 与 DATABASE_URL 是否配置。"""
    anon = no_bypass_client.get("/api/v1/health")
    assert anon.status_code == 200
    body = anon.json()
    assert body["schema"] == "034h"
    assert "env" not in body
    assert "database_url_set" not in body


def test_health_shows_config_to_authenticated(client):
    authed = client.get(
        "/api/v1/health",
        headers={"X-Dev-User": "smoke", "X-Dev-Tenant": "pilot"},
    )
    assert authed.status_code == 200
    assert "env" in authed.json()


def test_me_returns_authenticated_principal_without_credentials(client):
    response = client.get(
        "/api/v1/me",
        headers={"X-Dev-User": "smoke", "X-Dev-Tenant": "pilot"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sub"] == "smoke"
    assert body["tenant_slug"] == "pilot"
    assert "roles" in body
    assert "api_key" not in body


def test_saas_smoke_health_project_review(client):
    headers = {"X-Dev-User": "smoke", "X-Dev-Tenant": "pilot"}
    health = client.get("/api/v1/health", headers=headers)
    assert health.status_code == 200
    assert health.json().get("schema") == "034h"

    proj = client.post(
        "/api/v1/projects",
        headers=headers,
        json={"slug": "smoke", "name": "Smoke"},
    )
    assert proj.status_code == 201
    pid = proj.json()["id"]

    job = client.post(
        "/api/v1/jobs",
        headers=headers,
        json={"project_id": pid, "source_sha256": "e" * 64},
    )
    assert job.status_code == 201
    jid = job.json()["id"]

    enq = client.post(
        "/api/v1/review/enqueue",
        headers=headers,
        json={
            "job_id": jid,
            "segments": [
                {
                    "source_text": "Keep refs",
                    "machine_text": "x",
                    "policy": "PRESERVE",
                },
                {
                    "source_text": "Need review",
                    "machine_text": "需审",
                    "policy": "HUMAN_REVIEW",
                },
            ],
        },
    )
    assert enq.status_code == 200
    body = enq.json()
    assert body["count"] == 1
    assert any(s.get("reason") == "preserve" for s in body["skipped"])
