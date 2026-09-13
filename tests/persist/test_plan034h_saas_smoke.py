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


def test_saas_smoke_health_project_review(client):
    headers = {"X-Dev-User": "smoke", "X-Dev-Tenant": "pilot"}
    health = client.get("/api/v1/health")
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
