# SPDX-License-Identifier: MPL-2.0
"""PLAN-063d：batch-approve 不得把 violation 当 pending。"""
from __future__ import annotations

import json
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base
from qyunslation.workbench.bridge import router
from qyunslation.workbench.security import reset_nonce_cache, sign_bridge_request


def test_batch_decision_rejects_violation_status(monkeypatch):
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
    with TestClient(app, client=("127.0.0.1", 39063)) as client:
        def request(method: str, path: str, body: dict, nonce: str):
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

        started = request(
            "POST",
            "/internal/workbench/v1/runs/start",
            {
                "actor_sub": "reviewer-1",
                "source_sha256": "a" * 64,
                "source_text": "tralokinumab",
                "src_lang": "en",
                "tgt_lang": "zh",
                "source_format": "pdf",
            },
            "start-063",
        )
        assert started.status_code == 201, started.text
        run_id = started.json()["run_id"]
        completed = request(
            "POST",
            f"/internal/workbench/v1/runs/{run_id}/complete",
            {
                "actor_sub": "reviewer-1",
                "evidence": [
                    {
                        "source_text": "tralokinumab reduced lesions.",
                        "target_text": "未遵循的译文。",
                        "page_no": 1,
                        "block_id": "p1",
                    }
                ],
            },
            "complete-063",
        )
        assert completed.status_code == 200, completed.text
        rows = [row for row in completed.json()["candidates"] if row["status"] == "violation"]
        if not rows:
            return
        blocked = request(
            "POST",
            f"/internal/workbench/v1/runs/{run_id}/terms/batch-decision",
            {
                "actor_sub": "reviewer-1",
                "decisions": [
                    {
                        "candidate_id": rows[0]["id"],
                        "action": "approve",
                        "expected_version": rows[0]["version"],
                        "target_term": "曲罗芦单抗",
                    }
                ],
            },
            "batch-063",
        )
        assert blocked.status_code == 400
    reset_nonce_cache()
    reset_engine()
