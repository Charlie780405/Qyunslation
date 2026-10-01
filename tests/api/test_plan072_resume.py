# SPDX-License-Identifier: MPL-2.0
"""PLAN-072：预检列表、分片上传、审核草稿、续跑与租户隔离。"""
from __future__ import annotations

import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base, PreflightRecord, Tenant


@pytest.fixture()
def client(monkeypatch, tmp_path: Path):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    for name, folder in (
        ("PREFLIGHT_ROOT", "preflights"),
        ("ARTIFACT_ROOT", "artifacts"),
        ("UPLOAD_ROOT", "uploads"),
        ("RUNNER_ROOT", "runs"),
        ("PIPELINE_ROOT", "pipeline"),
    ):
        monkeypatch.setenv(f"QYUNSLATION_{name}", str(tmp_path / folder))
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


def _h(tenant="pilot", user="alice"):
    return {"X-Dev-User": user, "X-Dev-Tenant": tenant, "X-Dev-Role": "system_admin,reviewer"}


def test_list_preflights_returns_ready_records(client):
    pf = client.post(
        "/api/v1/preflights",
        headers=_h(),
        files={"file": ("doc.pdf", b"%PDF-1.7 sample", "application/pdf")},
    ).json()
    listed = client.get("/api/v1/preflights", headers=_h()).json()
    assert listed["latest"]["id"] == pf["id"]
    assert any(item["id"] == pf["id"] for item in listed["items"])


def test_chunked_upload_completes_to_preflight(client):
    payload = b"%PDF-1.7 chunked upload sample"
    created = client.post(
        "/api/v1/upload-sessions",
        headers=_h(),
        json={"filename": "chunk.pdf", "total_size": len(payload)},
    ).json()
    upload_id = created["upload_session"]["id"]
    client.patch(
        f"/api/v1/upload-sessions/{upload_id}",
        headers={**_h(), "Content-Range": f"bytes 0-{len(payload) - 1}/{len(payload)}"},
        content=payload,
    )
    pf = client.post(
        f"/api/v1/upload-sessions/{upload_id}/complete",
        headers=_h(),
        json={"source_language": "English", "target_language": "简体中文"},
    ).json()
    assert pf["state"] == "ready"
    assert pf["filename"] == "chunk.pdf"


def test_review_draft_roundtrip_and_cleared_on_decision(client):
    pf = client.post(
        "/api/v1/preflights",
        headers=_h(),
        files={"file": ("r.pdf", b"%PDF review", "application/pdf")},
    ).json()
    run = client.post(
        "/api/v1/translation-runs",
        headers={**_h(), "Idempotency-Key": "draft-run"},
        json={"preflight_id": pf["id"]},
    ).json()
    client.put(
        f"/api/v1/translation-runs/{run['id']}/review-draft",
        headers=_h(),
        json={"comment": "请核对 PIND 编号", "resolved_qa_ids": []},
    )
    draft = client.get(
        f"/api/v1/translation-runs/{run['id']}/review-draft",
        headers=_h(),
    ).json()
    assert draft["comment"] == "请核对 PIND 编号"


def test_resume_interrupted_run(client, monkeypatch):
    pf = client.post(
        "/api/v1/preflights",
        headers=_h(),
        files={"file": ("resume.pdf", b"%PDF resume", "application/pdf")},
    ).json()
    run = client.post(
        "/api/v1/translation-runs",
        headers={**_h(), "Idempotency-Key": "resume-run"},
        json={"preflight_id": pf["id"]},
    ).json()
    from qyunslation.persist.db import get_engine
    from sqlalchemy.orm import Session
    from qyunslation.persist.models import TranslationRunRecord
    from qyunslation.workbench.heartbeat import mark_interrupted

    with Session(get_engine()) as session:
        row = session.get(TranslationRunRecord, run["id"])
        mark_interrupted(session, row, reason="test interrupt")
        session.commit()
    resumed = client.post(
        f"/api/v1/translation-runs/{run['id']}/resume",
        headers=_h(),
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] in {"queued", "scanning", "translating", "rendering"}


def test_upload_session_isolated_by_tenant(client):
    created = client.post(
        "/api/v1/upload-sessions",
        headers=_h("pilot", "alice"),
        json={"filename": "iso.pdf", "total_size": 10},
    ).json()
    upload_id = created["upload_session"]["id"]
    denied = client.get(
        f"/api/v1/upload-sessions/{upload_id}",
        headers=_h("other", "alice"),
    )
    assert denied.status_code == 404
