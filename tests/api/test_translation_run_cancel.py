from __future__ import annotations

import json
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
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as current:
        yield current
    reset_engine()


def _headers():
    return {"X-Dev-User": "planner", "X-Dev-Tenant": "pilot"}


def _write_layout_complete_state(tmp_path: Path, *, run_id: str, tenant: str = "pilot") -> str:
    task_id = f"pdf2zh:{run_id}:1"
    run_dir = tmp_path / "runs" / tenant / run_id / "generation-1"
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "task_id": task_id,
        "tenant_id": tenant,
        "run_id": run_id,
        "generation": 1,
        "status": "layout_complete",
        "stage": "layout",
        "progress": None,
        "progress_message": "正在保存 PDF",
        "cli_complete": True,
    }
    (run_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return task_id


def test_cancel_layout_complete_run_stays_cancelled(client, monkeypatch, tmp_path: Path):
    from qyunslation.api import v1 as api_v1_module

    preflight = client.post(
        "/api/v1/preflights",
        headers=_headers(),
        files={"file": ("protocol.pdf", b"%PDF-1.7", "application/pdf")},
    ).json()

    async def stub_launch(*, run, preflight, target_language, **kwargs):
        run.external_task_id = _write_layout_complete_state(tmp_path, run_id=run.id)
        run.status = "translating"
        run.stage = "layout"
        run.progress = None
        run.quality_state = "qa_blocked"

    monkeypatch.setattr(api_v1_module, "_launch_translation_run", stub_launch)

    created = client.post(
        "/api/v1/translation-runs",
        headers={**_headers(), "Idempotency-Key": "layout-complete-cancel"},
        json={"preflight_id": preflight["id"]},
    )
    assert created.status_code == 201
    run_id = created.json()["id"]
    assert created.json()["status"] == "translating"

    cancelled = client.post(f"/api/v1/translation-runs/{run_id}/cancel", headers=_headers())
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    fetched = client.get(f"/api/v1/translation-runs/{run_id}", headers=_headers())
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "cancelled"

    listed = client.get("/api/v1/translation-runs", headers=_headers()).json()["items"]
    assert listed[0]["status"] == "cancelled"
