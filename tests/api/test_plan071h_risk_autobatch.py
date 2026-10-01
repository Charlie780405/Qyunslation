# SPDX-License-Identifier: MPL-2.0
"""PLAN-071h Task 4：高风险候选不能批量批准；低风险 exact 可受限批量批准。"""
from __future__ import annotations

import hashlib

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
    Base.metadata.create_all(init_engine("sqlite+pysqlite:///:memory:"))
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as current:
        yield current
    reset_engine()


H = {"X-Dev-User": "term-admin", "X-Dev-Tenant": "pilot", "X-Dev-Role": "system_admin,term_admin"}


def _job(client):
    project = client.post("/api/v1/projects", headers=H, json={"slug": "p1", "name": "P1"}).json()
    job = client.post(
        "/api/v1/jobs",
        headers=H,
        json={"project_id": project["id"], "source_sha256": hashlib.sha256(b"x").hexdigest()},
    )
    assert job.status_code == 201, job.text
    return job.json()["id"]


def _extract(client, job_id, *items):
    resp = client.post(
        f"/api/v1/jobs/{job_id}/terms/extract",
        headers=H,
        json={"candidates": list(items)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["created"]


def _approve(client, job_id, candidate):
    return client.post(
        f"/api/v1/jobs/{job_id}/terms/batch-decide",
        headers=H,
        json={
            "decisions": [
                {
                    "candidate_id": candidate["id"],
                    "action": "approve",
                    "expected_version": candidate["version"],
                    "target_term": candidate.get("suggested_target") or "译名",
                    "scope": "project",
                }
            ]
        },
    )


def test_high_risk_candidate_cannot_be_batch_approved(client):
    job_id = _job(client)
    (high,) = _extract(
        client,
        job_id,
        {
            "source_term": "dupilumab",
            "suggested_target": "度普利尤单抗",
            "term_type": "drug",
            "risk": "high",
            "match_type": "exact",
            "confidence": 0.99,
        },
    )
    resp = _approve(client, job_id, high)
    assert resp.status_code == 400
    assert "not eligible" in resp.json()["detail"]


def test_semantic_candidate_cannot_be_batch_approved(client):
    job_id = _job(client)
    (cand,) = _extract(
        client,
        job_id,
        {"source_term": "wibble", "suggested_target": "威布尔", "risk": "normal", "match_type": "llm"},
    )
    assert _approve(client, job_id, cand).status_code == 400


def test_low_risk_exact_candidate_can_be_batch_approved(client):
    job_id = _job(client)
    (low,) = _extract(
        client,
        job_id,
        {
            "source_term": "placebo",
            "suggested_target": "安慰剂",
            "risk": "normal",
            "match_type": "exact",
            "confidence": 0.99,
        },
    )
    resp = _approve(client, job_id, low)
    assert resp.status_code == 200, resp.text
