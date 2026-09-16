# SPDX-License-Identifier: MPL-2.0
"""PLAN-064：拒绝后同形/词缀变体不再进待确认。"""
from __future__ import annotations

import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base
from qyunslation.workbench.bridge import router
from qyunslation.workbench.security import reset_nonce_cache, sign_bridge_request


@pytest.fixture()
def client(monkeypatch):
    reset_engine()
    reset_nonce_cache()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_TERM_BRIDGE_SECRET", "test-bridge-secret")
    monkeypatch.setenv("QYUNSLATION_WORKBENCH_TENANT", "qyuns-test")
    monkeypatch.setenv("QYUNSLATION_TERM_SUGGEST", "0")
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app, client=("127.0.0.1", 39064)) as current:
        yield current
    reset_nonce_cache()
    reset_engine()


def _request(client, method: str, path: str, body: dict, *, nonce: str):
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = sign_bridge_request(
        method=method,
        path=path.partition("?")[0],
        body=raw,
        secret="test-bridge-secret",
        nonce=nonce,
        timestamp=int(time.time()),
    )
    return client.request(method, path, content=raw, headers=headers)


def _start(client, *, source_text: str, digest: str, nonce: str) -> dict:
    response = _request(
        client,
        "POST",
        "/internal/workbench/v1/runs/start",
        {
            "actor_sub": "reviewer-1",
            "source_sha256": digest,
            "source_text": source_text,
            "src_lang": "en",
            "tgt_lang": "zh",
            "source_format": "pdf",
        },
        nonce=nonce,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _complete(client, run_id: str, source_term: str, *, nonce: str):
    return _request(
        client,
        "POST",
        f"/internal/workbench/v1/runs/{run_id}/complete",
        {
            "actor_sub": "reviewer-1",
            "evidence": [
                {
                    "source_text": f"{source_term} reduced lesions.",
                    "target_text": "曲罗芦单抗减少皮损。",
                    "source_term": source_term,
                    "target_term": "曲罗芦单抗",
                    "page_no": 1,
                    "block_id": "p1",
                }
            ],
        },
        nonce=nonce,
    )


def test_rejected_prefixed_form_does_not_reenter_or_kill_stem(client):
    first = _start(
        client,
        source_text="anti-tralokinumab-pending reduced lesions.",
        digest="c" * 64,
        nonce="start-064-a",
    )
    completed = _complete(client, first["run_id"], "anti-tralokinumab-pending", nonce="complete-064-a")
    assert completed.status_code == 200, completed.text
    pending = [row for row in completed.json()["candidates"] if row["status"] == "pending"]
    assert pending
    rejected = _request(
        client,
        "POST",
        f"/internal/workbench/v1/runs/{first['run_id']}/terms/{pending[0]['id']}/decision",
        {
            "actor_sub": "reviewer-1",
            "action": "reject",
            "expected_version": pending[0]["version"],
            "note": "不必入库",
        },
        nonce="reject-064-a",
    )
    assert rejected.status_code == 200, rejected.text

    second = _start(
        client,
        source_text="anti-tralokinumab-pending and tralokinumab reduced lesions.",
        digest="d" * 64,
        nonce="start-064-b",
    )
    replay = _complete(client, second["run_id"], "anti-tralokinumab-pending", nonce="complete-064-b")
    assert replay.status_code == 200, replay.text
    names = {row["source_term"] for row in replay.json()["candidates"] if row["status"] == "pending"}
    assert "anti-tralokinumab-pending" not in names

    third = _start(
        client,
        source_text="tralokinumab reduced lesions.",
        digest="f" * 64,
        nonce="start-064-c",
    )
    keep = _complete(client, third["run_id"], "tralokinumab", nonce="complete-064-c")
    assert keep.status_code == 200, keep.text
    keep_names = {row["source_term"] for row in keep.json()["candidates"] if row["status"] == "pending"}
    assert "tralokinumab" in keep_names


def test_batch_reject_allows_non_exact_pending(client):
    started = _start(
        client,
        source_text="dermatitis was assessed.",
        digest="e" * 64,
        nonce="start-064-batch",
    )
    completed = _complete(client, started["run_id"], "dermatitis", nonce="complete-064-batch")
    assert completed.status_code == 200, completed.text
    pending = [row for row in completed.json()["candidates"] if row["status"] == "pending"]
    assert pending
    blocked = _request(
        client,
        "POST",
        f"/internal/workbench/v1/runs/{started['run_id']}/terms/batch-decision",
        {
            "actor_sub": "reviewer-1",
            "decisions": [
                {
                    "candidate_id": pending[0]["id"],
                    "action": "reject",
                    "expected_version": pending[0]["version"],
                }
            ],
        },
        nonce="batch-064-reject",
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["count"] == 1
    assert blocked.json()["decided"][0]["candidate"]["status"] == "rejected"
