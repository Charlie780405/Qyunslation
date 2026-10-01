# SPDX-License-Identifier: MPL-2.0
"""PLAN-071i/g：租户灰度、快照只读与重试不改写旧快照。"""
from __future__ import annotations

import os
import stat
import time
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
    for name, folder in (
        ("PREFLIGHT_ROOT", "preflights"),
        ("ARTIFACT_ROOT", "artifacts"),
        ("RUNNER_ROOT", "runs"),
        ("PIPELINE_ROOT", "pipeline"),
    ):
        monkeypatch.setenv(f"QYUNSLATION_{name}", str(tmp_path / folder))
    monkeypatch.setenv("QYUNSLATION_PIPELINE", "legacy")
    monkeypatch.setenv("QYUNSLATION_PIPELINE_TENANTS", "pilot")
    cli = tmp_path / "cli"
    cli.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "a = sys.argv[1:]\n"
        "out = pathlib.Path(a[a.index('--output') + 1]); out.mkdir(parents=True, exist_ok=True)\n"
        "(out / (pathlib.Path(a[-1]).stem + '_dual.pdf')).write_bytes(b'%PDF fake')\n",
        encoding="utf-8",
    )
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("QYUNSLATION_PDF2ZH_CLI", str(cli))
    Base.metadata.create_all(init_engine("sqlite+pysqlite:///:memory:"))
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as current:
        yield current
    reset_engine()


def _h(tenant="pilot"):
    return {"X-Dev-User": "u", "X-Dev-Tenant": tenant, "X-Dev-Role": "system_admin,reviewer"}


def _create(client, tenant, key, content=b"%PDF-1.7 a"):
    pf = client.post(
        "/api/v1/preflights",
        headers=_h(tenant),
        files={"file": ("p.pdf", content + key.encode(), "application/pdf")},
    ).json()
    resp = client.post(
        "/api/v1/translation-runs",
        headers={**_h(tenant), "Idempotency-Key": key},
        json={"preflight_id": pf["id"]},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_allowlisted_tenant_gets_v2_and_others_stay_legacy(client):
    pilot = _create(client, "pilot", "k-pilot")
    other = _create(client, "ordinary", "k-ordinary")
    assert pilot["settings"]["pipeline"] == "v2"
    assert pilot["manifest_version"]
    assert other["settings"]["pipeline"] == "legacy"
    assert not other["manifest_version"]


def test_rollback_does_not_flip_inflight_runs(client, monkeypatch):
    run = _create(client, "pilot", "k-inflight")
    monkeypatch.setenv("QYUNSLATION_PIPELINE_TENANTS", "")
    again = client.get(f"/api/v1/translation-runs/{run['id']}", headers=_h()).json()
    assert again["settings"]["pipeline"] == "v2"
    fresh = _create(client, "pilot", "k-after-rollback")
    assert fresh["settings"]["pipeline"] == "legacy"


def test_run_snapshot_has_model_egress_and_version_fields(client):
    snap = _create(client, "pilot", "k-snap")["settings"]["model_snapshot"]
    assert snap["profile_id"] == "internal-qwen-quality"
    assert snap["provider"] == "ollama" and snap["model_id"]
    assert snap["prompt_version"] and snap["termbase_version"]
    assert snap["document_classification"] == "internal"
    assert snap["egress_scope"] == "none"
    assert snap["version_pinned"] is False and snap["reported_version"] is None
    assert "patch_fingerprint" in snap


def test_retry_v2_does_not_touch_old_snapshot_or_global_env(client, monkeypatch):
    run = _create(client, "ordinary", "k-legacy-src")
    assert run["settings"]["pipeline"] == "legacy"
    old_snapshot = dict(run["settings"])
    for _ in range(100):
        time.sleep(0.05)
        state = client.get(f"/api/v1/translation-runs/{run['id']}", headers=_h("ordinary")).json()
        if state["status"] in {"succeeded", "failed", "blocked", "degraded"}:
            break
    assert state["status"] == "succeeded" and state["quality_state"] == "legacy_unverified"
    before = os.environ.get("QYUNSLATION_PIPELINE")
    retry = client.post(
        f"/api/v1/translation-runs/{run['id']}/retry", headers=_h("ordinary"), json={"pipeline": "v2"}
    )
    assert retry.status_code == 201, retry.text
    assert retry.json()["settings"]["pipeline"] == "v2"
    assert retry.json()["generation"] == 2
    assert os.environ.get("QYUNSLATION_PIPELINE") == before
    old = client.get(f"/api/v1/translation-runs/{run['id']}", headers=_h("ordinary")).json()
    assert old["settings"] == old_snapshot
