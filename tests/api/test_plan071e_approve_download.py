# SPDX-License-Identifier: MPL-2.0
"""PLAN-071e：批准后才物化正式产物并解锁下载。"""
from __future__ import annotations

import stat
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base


def _fake_cli(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "out = pathlib.Path(args[args.index('--output') + 1])\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "src = pathlib.Path(args[-1])\n"
        "(out / (src.stem + '_dual.pdf')).write_bytes(b'%PDF fake translated')\n"
        "print('Progress: 1.0, export', flush=True)\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


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
    monkeypatch.setenv("QYUNSLATION_PIPELINE", "v2")
    cli = tmp_path / "fake-pdf2zh"
    _fake_cli(cli)
    monkeypatch.setenv("QYUNSLATION_PDF2ZH_CLI", str(cli))
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as current:
        yield current
    reset_engine()


def _headers():
    return {"X-Dev-User": "planner", "X-Dev-Tenant": "pilot"}


def test_v2_approve_materializes_formal_artifact_and_unlocks_download(client):
    headers = {**_headers(), "X-Dev-Role": "system_admin,reviewer"}
    preflight = client.post(
        "/api/v1/preflights",
        headers=headers,
        files={"file": ("protocol.pdf", b"%PDF-1.7", "application/pdf")},
    ).json()
    created = client.post(
        "/api/v1/translation-runs",
        headers={**headers, "Idempotency-Key": "pdf-v2-approve"},
        json={"preflight_id": preflight["id"]},
    ).json()
    run_id = created["id"]
    state = created
    for _ in range(300):
        time.sleep(0.05)
        state = client.get(f"/api/v1/translation-runs/{run_id}", headers=headers).json()
        if state["quality_state"] == "review_ready":
            break
    assert state["quality_state"] == "review_ready", (state["status"], state["stage"], state["quality_state"], state.get("degradation_reason"))
    assert not any(a["formal_export"] for a in state.get("artifacts") or [])

    approved = client.post(
        f"/api/v1/translation-runs/{run_id}/review-decision",
        headers=headers,
        json={"decision": "approve"},
    )
    assert approved.status_code == 200, approved.text
    after = client.get(f"/api/v1/translation-runs/{run_id}", headers=headers).json()
    assert after["status"] == "succeeded"
    assert after["quality_state"] == "approved"
    formal = [a for a in after["artifacts"] if a["formal_export"]]
    assert formal
    download = client.get(formal[0]["download_url"], headers=headers)
    assert download.status_code == 200
