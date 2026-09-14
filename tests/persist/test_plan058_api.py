# SPDX-License-Identifier: MPL-2.0
"""PLAN-058：术语解析、候选提取和人工裁决 API。"""
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
    with TestClient(app) as current:
        yield current
    reset_engine()


def _setup(client, headers):
    project = client.post(
        "/api/v1/projects", json={"slug": "terms", "name": "Terms"}, headers=headers
    ).json()
    job = client.post(
        "/api/v1/jobs",
        json={"project_id": project["id"], "source_sha256": "b" * 64},
        headers=headers,
    ).json()
    return project["id"], job["id"]


def test_term_extract_review_and_exact_resolve(client):
    headers = {"X-Dev-User": "reviewer", "X-Dev-Tenant": "term-tenant"}
    project_id, job_id = _setup(client, headers)

    before = client.post(
        "/api/v1/terms/resolve",
        json={"project_id": project_id, "source_text": "The primary endpoint was met."},
        headers=headers,
    )
    assert before.status_code == 200, before.text
    assert before.json()["matches"] == []

    extracted = client.post(
        f"/api/v1/jobs/{job_id}/terms/extract",
        json={
            "termbase_version": "v0",
            "candidates": [
                {
                    "source_term": "primary endpoint",
                    "observed_target": "主要终点评估",
                    "suggested_target": "主要终点",
                    "term_type": "endpoint",
                    "confidence": 0.91,
                    "occurrences": [{"page_no": 2, "block_id": "p2-b1"}],
                }
            ],
        },
        headers=headers,
    )
    assert extracted.status_code == 201, extracted.text
    candidate = extracted.json()["created"][0]
    assert candidate["occurrences"][0]["page_no"] == 2

    queued = client.get(f"/api/v1/jobs/{job_id}/terms", headers=headers)
    assert queued.status_code == 200
    assert len(queued.json()) == 1

    decided = client.post(
        f"/api/v1/jobs/{job_id}/terms/{candidate['id']}/decide",
        json={
            "action": "approve",
            "expected_version": 1,
            "target_term": "主要终点评估",
        },
        headers=headers,
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["candidate"]["status"] == "approved"

    after = client.post(
        "/api/v1/terms/resolve",
        json={"project_id": project_id, "source_text": "The primary endpoint was met."},
        headers=headers,
    )
    assert after.status_code == 200, after.text
    assert after.json()["matches"][0]["target_term"] == "主要终点评估"
    assert after.json()["matches"][0]["match_type"] == "exact"

    summary = client.get(f"/api/v1/jobs/{job_id}/term-review-summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["approved"] == 1
    assert summary.json()["formal_gate"]["passed"] is True


def test_term_endpoints_reject_cross_tenant_job(client):
    owner = {"X-Dev-User": "owner", "X-Dev-Tenant": "owner-tenant"}
    other = {"X-Dev-User": "other", "X-Dev-Tenant": "other-tenant"}
    _, job_id = _setup(client, owner)
    response = client.get(f"/api/v1/jobs/{job_id}/terms", headers=other)
    assert response.status_code == 404


def test_term_resolve_requires_project_tenant_scope(client):
    owner = {"X-Dev-User": "owner", "X-Dev-Tenant": "owner-tenant"}
    other = {"X-Dev-User": "other", "X-Dev-Tenant": "other-tenant"}
    project_id, _ = _setup(client, owner)
    response = client.post(
        "/api/v1/terms/resolve",
        json={"project_id": project_id, "source_text": "primary endpoint"},
        headers=other,
    )
    assert response.status_code == 404


def test_elevated_term_scope_requires_term_admin(client):
    headers = {"X-Dev-User": "reviewer", "X-Dev-Tenant": "term-tenant"}
    project_id, job_id = _setup(client, headers)
    extracted = client.post(
        f"/api/v1/jobs/{job_id}/terms/extract",
        json={"candidates": [{"source_term": "target", "observed_target": "靶点"}]},
        headers=headers,
    )
    candidate = extracted.json()["created"][0]
    response = client.post(
        f"/api/v1/jobs/{job_id}/terms/{candidate['id']}/decide",
        json={
            "action": "approve",
            "expected_version": 1,
            "target_term": "靶点",
            "scope": "org",
        },
        headers=headers,
    )
    assert response.status_code == 403


def test_high_risk_candidate_requires_admin_after_submission(client):
    headers = {"X-Dev-User": "reviewer", "X-Dev-Tenant": "term-tenant"}
    project_id, job_id = _setup(client, headers)
    extracted = client.post(
        f"/api/v1/jobs/{job_id}/terms/extract",
        json={
            "candidates": [
                {
                    "source_term": "ABC-101",
                    "observed_target": "ABC-101",
                    "risk": "high",
                    "term_type": "protocol",
                }
            ]
        },
        headers=headers,
    )
    candidate = extracted.json()["created"][0]
    direct = client.post(
        f"/api/v1/jobs/{job_id}/terms/{candidate['id']}/decide",
        json={"action": "approve", "expected_version": 1, "target_term": "ABC-101"},
        headers=headers,
    )
    assert direct.status_code == 403

    submitted = client.post(
        f"/api/v1/jobs/{job_id}/terms/{candidate['id']}/decide",
        json={"action": "submit_for_admin", "expected_version": 1},
        headers=headers,
    )
    assert submitted.status_code == 200
    assert submitted.json()["candidate"]["status"] == "pending_admin"
