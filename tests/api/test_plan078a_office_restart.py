"""PLAN-078a / H2: an Office (non-PDF) run waiting at the quality gate survives a sidecar restart."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from _plan078_flow import ADMIN
from qyunslation.api import v1 as api_v1_module
from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist import db as persist_db
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base, TranslationRunRecord


@pytest.fixture()
def client(monkeypatch, tmp_path: Path):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    monkeypatch.setenv("QYUNSLATION_PIPELINE", "v2")
    for name, folder in (
        ("PREFLIGHT_ROOT", "preflights"),
        ("ARTIFACT_ROOT", "artifacts"),
        ("RUNNER_ROOT", "runs"),
        ("PIPELINE_ROOT", "pipeline"),
    ):
        monkeypatch.setenv(f"QYUNSLATION_{name}", str(tmp_path / folder))
    Base.metadata.create_all(init_engine("sqlite+pysqlite:///:memory:"))
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as current:
        yield current
    reset_engine()


def _run(client, run_id):
    return client.get(f"/api/v1/translation-runs/{run_id}", headers=ADMIN).json()


def _office_run(client, monkeypatch, tmp_path, alive):
    output = tmp_path / "protocol_translated.txt"
    output.write_text("临床文本译文", encoding="utf-8")
    from qyunslation import server as server_module

    class FakeService:
        main_event_loop = object()

        async def start_translation(self, **kwargs):
            return {"task_id": "office-task"}

        def get_task_state(self, task_id):
            if not alive["on"]:
                return None  # the sidecar restarted or released the task
            return {
                "download_ready": True,
                "is_processing": False,
                "error_flag": False,
                "original_filename": "protocol.txt",
                "downloadable_files": {"txt": {"path": str(output), "filename": output.name}},
                "attachment_files": {},
            }

        def cancel_task(self, task_id):
            return {"cancelled": True}

    monkeypatch.setattr(server_module, "get_translation_service", lambda: FakeService())
    pf = client.post(
        "/api/v1/preflights", headers=ADMIN, files={"file": ("protocol.txt", b"clinical text", "text/plain")}
    ).json()
    run_id = client.post(
        "/api/v1/translation-runs",
        headers={**ADMIN, "Idempotency-Key": "office-restart"},
        json={"preflight_id": pf["id"], "direction": "English → 简体中文", "profile": "临床研究文档"},
    ).json()["id"]
    return run_id, output


def test_office_run_at_the_gate_survives_a_sidecar_restart(client, monkeypatch, tmp_path):
    alive = {"on": True}
    run_id, output = _office_run(client, monkeypatch, tmp_path, alive)
    gated = _run(client, run_id)
    assert gated["status"] == "gated" and gated["quality_state"] == "review_ready"

    alive["on"] = False  # restart: the in-memory task is gone ...
    output.unlink()  # ... and so is the temp output it owned
    with persist_db.SessionLocal() as session:
        run = session.get(TranslationRunRecord, run_id)
        run.heartbeat_at = None
        session.commit()
    for _ in range(3):
        again = _run(client, run_id)
        assert again["status"] == "gated", again["status"]  # not "interrupted"
        assert again["lifecycle"] == "review"

    approved = client.post(
        f"/api/v1/translation-runs/{run_id}/review-decision", headers=ADMIN, json={"decision": "approve"}
    )
    assert approved.status_code == 200, approved.text
    formal = [a for a in approved.json()["artifacts"] if a["formal_export"]]
    assert len(formal) == 1
    downloaded = client.get(formal[0]["download_url"], headers=ADMIN)
    assert downloaded.status_code == 200
    assert downloaded.content.decode("utf-8") == "临床文本译文"


def test_persisted_outputs_can_be_cleared_for_a_resume(client, monkeypatch, tmp_path):
    run_id, _ = _office_run(client, monkeypatch, tmp_path, {"on": True})
    assert _run(client, run_id)["status"] == "gated"
    with persist_db.SessionLocal() as session:
        run = session.get(TranslationRunRecord, run_id)
        assert api_v1_module._persisted_executor_state(run) is not None
        api_v1_module._clear_persisted_executor_outputs(run)
        assert api_v1_module._persisted_executor_state(run) is None
