# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base

PDF = b"%PDF-1.7\n" + b"0123456789" * 40


@pytest.fixture()
def client(monkeypatch, tmp_path: Path):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    for name, folder in (
        ("PREFLIGHT_ROOT", "preflights"),
        ("ARTIFACT_ROOT", "artifacts"),
        ("RUNNER_ROOT", "runs"),
        ("PIPELINE_ROOT", "pipeline"),
    ):
        monkeypatch.setenv(f"QYUNSLATION_{name}", str(tmp_path / folder))
    monkeypatch.setenv("QYUNSLATION_PIPELINE", "legacy")
    Base.metadata.create_all(init_engine("sqlite+pysqlite:///:memory:"))
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as current:
        yield current
    reset_engine()


def _headers(tenant="pilot", user="owner"):
    return {"X-Dev-User": user, "X-Dev-Tenant": tenant, "X-Dev-Role": "reviewer"}


@pytest.fixture()
def run_id(client):
    pf = client.post(
        "/api/v1/preflights",
        headers=_headers(),
        files={"file": ("p.pdf", PDF, "application/pdf")},
    ).json()
    created = client.post(
        "/api/v1/translation-runs",
        headers={**_headers(), "Idempotency-Key": "range-1"},
        json={"preflight_id": pf["id"]},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_source_preview_is_inline_and_hides_paths(client, run_id):
    resp = client.get(f"/api/v1/translation-runs/{run_id}/preview/source", headers=_headers())
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["content-disposition"].startswith("inline")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "storage" not in resp.headers.get("content-disposition", "").lower()
    assert resp.content == PDF


def test_source_preview_supports_range(client, run_id):
    resp = client.get(
        f"/api/v1/translation-runs/{run_id}/preview/source",
        headers={**_headers(), "Range": "bytes=0-9"},
    )
    assert resp.status_code == 206
    assert resp.content == PDF[:10]
    assert resp.headers["content-range"].startswith("bytes 0-9/")
    assert resp.headers["accept-ranges"] == "bytes"


def test_unsatisfiable_range_is_416(client, run_id):
    resp = client.get(
        f"/api/v1/translation-runs/{run_id}/preview/source",
        headers={**_headers(), "Range": "bytes=999999-"},
    )
    assert resp.status_code == 416


def test_cross_tenant_and_other_user_cannot_preview(client, run_id):
    other_tenant = client.get(
        f"/api/v1/translation-runs/{run_id}/preview/source", headers=_headers(tenant="other")
    )
    assert other_tenant.status_code == 404
    plain_user = client.get(
        f"/api/v1/translation-runs/{run_id}/preview/source",
        headers={"X-Dev-User": "intruder", "X-Dev-Tenant": "pilot", "X-Dev-Role": "translator"},
    )
    assert plain_user.status_code == 404


def test_unknown_side_and_missing_translation(client, run_id):
    assert client.get(f"/api/v1/translation-runs/{run_id}/preview/bogus", headers=_headers()).status_code == 404
    assert client.get(f"/api/v1/translation-runs/{run_id}/preview/translated", headers=_headers()).status_code == 404


def test_unauthenticated_request_is_rejected(client, run_id, monkeypatch):
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "0")
    resp = client.get(f"/api/v1/translation-runs/{run_id}/preview/source")
    assert resp.status_code in {401, 403, 503}
    assert resp.content != PDF
