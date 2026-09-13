# SPDX-License-Identifier: MPL-2.0
"""PLAN-034c：/api/v1 与 /service 并存。"""
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

    # 并存证明：挂一个最小 /service/meta
    from fastapi import APIRouter

    service = APIRouter(prefix="/service")

    @service.get("/meta")
    def meta():
        return {"service": "ok", "plan": "034c"}

    app.include_router(service)

    with TestClient(app) as c:
        yield c
    reset_engine()


def test_health_and_service_coexist(client):
    h = client.get("/api/v1/health")
    assert h.status_code == 200
    body = h.json()
    assert body["schema"] in {"034c", "034d"}
    assert body["db"] == "ok"
    m = client.get("/service/meta")
    assert m.status_code == 200
    assert m.json()["service"] == "ok"


def test_project_job_flow(client):
    headers = {"X-Dev-User": "alice", "X-Dev-Tenant": "t1"}
    r = client.post(
        "/api/v1/projects",
        json={"slug": "demo", "name": "Demo"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    project_id = r.json()["id"]
    digest = "c" * 64
    j = client.post(
        "/api/v1/jobs",
        json={"project_id": project_id, "source_sha256": digest, "storage_key": "k/1"},
        headers=headers,
    )
    assert j.status_code == 201, j.text
    job_id = j.json()["id"]
    g = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert g.status_code == 200
    assert g.json()["source_sha256"] == digest
    listed = client.get(f"/api/v1/jobs?project_id={project_id}", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
