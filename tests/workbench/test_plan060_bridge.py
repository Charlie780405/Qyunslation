# SPDX-License-Identifier: MPL-2.0
"""PLAN-060：工作台术语桥接的端到端安全和治理行为。"""
from __future__ import annotations

import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base, UserMembership
from qyunslation.workbench.bridge import router
from qyunslation.workbench.security import reset_nonce_cache, sign_bridge_request


@pytest.fixture()
def client(monkeypatch):
    reset_engine()
    reset_nonce_cache()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_TERM_BRIDGE_SECRET", "test-bridge-secret")
    monkeypatch.setenv("QYUNSLATION_WORKBENCH_TENANT", "qyuns-test")
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app, client=("127.0.0.1", 39060)) as current:
        yield current
    reset_nonce_cache()
    reset_engine()


def _request(client, method: str, path: str, body: dict, *, nonce: str = "nonce-060"):
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = sign_bridge_request(
        method=method,
        path=path,
        body=raw,
        secret="test-bridge-secret",
        nonce=nonce,
        timestamp=int(time.time()),
    )
    return client.request(method, path, content=raw, headers=headers)


def _start(client, *, source_text: str, nonce: str = "start-060") -> dict:
    response = _request(
        client,
        "POST",
        "/internal/workbench/v1/runs/start",
        {
            "actor_sub": "reviewer-1",
            "source_sha256": "a" * 64,
            "source_text": source_text,
            "src_lang": "en",
            "tgt_lang": "zh",
            "source_format": "pdf",
        },
        nonce=nonce,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_bridge_rejects_unsigned_and_replayed_requests(client):
    body = {
        "actor_sub": "reviewer-1",
        "source_sha256": "a" * 64,
        "source_text": "primary endpoint",
        "src_lang": "en",
        "tgt_lang": "zh",
        "source_format": "pdf",
    }
    unsigned = client.post("/internal/workbench/v1/runs/start", json=body)
    assert unsigned.status_code == 401

    first = _request(
        client,
        "POST",
        "/internal/workbench/v1/runs/start",
        body,
        nonce="replayed-060",
    )
    assert first.status_code == 201, first.text
    replay = _request(
        client,
        "POST",
        "/internal/workbench/v1/runs/start",
        body,
        nonce="replayed-060",
    )
    assert replay.status_code == 409


def test_normal_confirmation_enters_company_library_and_reuses_next_file(client):
    first = _start(client, source_text="The primary endpoint was met.")
    run_id = first["run_id"]
    completed = _request(
        client,
        "POST",
        f"/internal/workbench/v1/runs/{run_id}/complete",
        {
            "actor_sub": "reviewer-1",
            "evidence": [
                {
                    "source_text": "primary endpoint",
                    "target_text": "主要终点评估",
                    "source_term": "primary endpoint",
                    "target_term": "主要终点评估",
                    "role": "body",
                    "page_no": 2,
                    "block_id": "p2-b1",
                }
            ]
        },
        nonce="complete-normal-060",
    )
    assert completed.status_code == 200, completed.text
    candidate = completed.json()["candidates"][0]
    assert candidate["status"] == "pending"

    decided = _request(
        client,
        "POST",
        f"/internal/workbench/v1/runs/{run_id}/terms/{candidate['id']}/decision",
        {
            "actor_sub": "reviewer-1",
            "action": "approve",
            "expected_version": 1,
            "target_term": "主要终点评估",
        },
        nonce="approve-normal-060",
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["candidate"]["status"] == "approved"

    next_run = _start(
        client,
        source_text="The primary endpoint is evaluated again.",
        nonce="next-run-060",
    )
    hard_terms = next_run["policy"]["hard_terms"]
    assert hard_terms == {"primary endpoint": "主要终点评估"}
    assert next_run["policy"]["semantic_used"] is False


def test_high_risk_term_requires_admin_final_review(client):
    started = _start(client, source_text="ABC-101 was administered.")
    run_id = started["run_id"]
    completed = _request(
        client,
        "POST",
        f"/internal/workbench/v1/runs/{run_id}/complete",
        {
            "actor_sub": "reviewer-1",
            "evidence": [
                {
                    "source_text": "ABC-101",
                    "target_text": "ABC-101",
                    "source_term": "ABC-101",
                    "target_term": "ABC-101",
                    "role": "body",
                    "page_no": 1,
                    "block_id": "p1-b1",
                }
            ]
        },
        nonce="complete-high-060",
    )
    candidate = completed.json()["candidates"][0]
    assert candidate["risk"] == "high"

    direct = _request(
        client,
        "POST",
        f"/internal/workbench/v1/runs/{run_id}/terms/{candidate['id']}/decision",
        {
            "actor_sub": "reviewer-1",
            "action": "approve",
            "expected_version": 1,
            "target_term": "ABC-101",
        },
        nonce="approve-high-060",
    )
    assert direct.status_code == 403

    submitted = _request(
        client,
        "POST",
        f"/internal/workbench/v1/runs/{run_id}/terms/{candidate['id']}/decision",
        {"actor_sub": "reviewer-1", "action": "submit_for_admin", "expected_version": 1},
        nonce="submit-high-060",
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["candidate"]["status"] == "pending_admin"

    from qyunslation.persist.db import SessionLocal

    assert SessionLocal is not None
    with SessionLocal() as session:
        membership = session.query(UserMembership).filter_by(user_sub="reviewer-1").one()
        membership.role = "term_admin"
        session.commit()

    final = _request(
        client,
        "POST",
        f"/internal/workbench/v1/runs/{run_id}/terms/{candidate['id']}/decision",
        {
            "actor_sub": "reviewer-1",
            "action": "approve",
            "expected_version": 2,
            "target_term": "ABC-101",
        },
        nonce="final-high-060",
    )
    assert final.status_code == 200, final.text
    assert final.json()["candidate"]["status"] == "approved"
