# SPDX-License-Identifier: MPL-2.0
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
    monkeypatch.setenv("QYUNSLATION_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("QYUNSLATION_RUNNER_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("QYUNSLATION_PIPELINE_ROOT", str(tmp_path / "pipeline"))
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as current:
        yield current
    reset_engine()


def _headers():
    return {"X-Dev-User": "planner", "X-Dev-Tenant": "pilot"}


def test_internal_rejects_deepseek_full_doc(client):
    preflight = client.post(
        "/api/v1/preflights",
        headers=_headers(),
        files={"file": ("protocol.pdf", b"%PDF-1.7", "application/pdf")},
    ).json()
    patched = client.patch(
        f"/api/v1/preflights/{preflight['id']}",
        headers=_headers(),
        json={
            "document_classification": "internal",
            "model_profile_id": "public-deepseek-flash",
        },
    )
    assert patched.status_code in {400, 403, 422}


def test_model_profiles_filter_by_classification(client):
    resp = client.get("/api/v1/model-profiles?classification=confidential", headers=_headers())
    assert resp.status_code == 200
    ids = {item["profile_id"] for item in resp.json()["items"]}
    assert ids == {"internal-qwen-quality"}
