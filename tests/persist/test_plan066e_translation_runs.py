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
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as current:
        yield current
    reset_engine()


def headers():
    return {"X-Dev-User": "planner", "X-Dev-Tenant": "pilot"}


def test_translation_run_is_durable_and_idempotent_when_runner_is_unavailable(client):
    preflight = client.post(
        "/api/v1/preflights",
        headers=headers(),
        files={"file": ("protocol.txt", b"clinical text", "text/plain")},
    ).json()
    body = {"preflight_id": preflight["id"], "direction": "English → 简体中文", "profile": "临床研究文档"}
    first = client.post(
        "/api/v1/translation-runs",
        headers={**headers(), "Idempotency-Key": "run-once"},
        json=body,
    )
    assert first.status_code == 201
    assert first.json()["status"] == "blocked"
    assert first.json()["degradation_reason"] == "translation runner unavailable"
    second = client.post(
        "/api/v1/translation-runs",
        headers={**headers(), "Idempotency-Key": "run-once"},
        json=body,
    )
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    listing = client.get("/api/v1/translation-runs", headers=headers())
    assert listing.status_code == 200
    assert listing.json()["items"][0]["preflight_id"] == preflight["id"]
    assert client.get(
        "/api/v1/translation-runs", headers={"X-Dev-User": "other", "X-Dev-Tenant": "pilot"}
    ).json()["items"] == []


def test_retry_allocates_new_generation_without_overwriting_original(client):
    preflight = client.post(
        "/api/v1/preflights",
        headers=headers(),
        files={"file": ("protocol.txt", b"clinical text", "text/plain")},
    ).json()
    created = client.post(
        "/api/v1/translation-runs",
        headers=headers(),
        json={"preflight_id": preflight["id"]},
    ).json()
    retry = client.post(f"/api/v1/translation-runs/{created['id']}/retry", headers=headers())
    assert retry.status_code == 201
    assert retry.json()["generation"] == 2
    assert retry.json()["id"] != created["id"]
    repeated = client.post(f"/api/v1/translation-runs/{created['id']}/retry", headers=headers())
    assert repeated.status_code == 201
    assert repeated.json()["id"] == retry.json()["id"]
    assert len(client.get("/api/v1/translation-runs", headers=headers()).json()["items"]) == 2


def test_completed_runner_outputs_are_copied_and_downloaded_by_opaque_artifact_id(
    client, monkeypatch
):
    preflight = client.post(
        "/api/v1/preflights",
        headers=headers(),
        files={"file": ("protocol.txt", b"translated clinical text", "text/plain")},
    ).json()
    from qyunslation import server as server_module

    class FakeService:
        main_event_loop = object()

        def __init__(self):
            self.path = None

        async def start_translation(self, **kwargs):
            self.path = kwargs["file_contents"]
            return {"task_id": "fake-task"}

        def get_task_state(self, task_id):
            assert task_id == "fake-task"
            return {
                "download_ready": True,
                "is_processing": False,
                "error_flag": False,
                "original_filename": "protocol.txt",
                "downloadable_files": {
                    "txt": {"path": str(preflight_file), "filename": "protocol_translated.txt"}
                },
                "attachment_files": {},
            }

        def cancel_task(self, task_id):
            return {"cancelled": True}

    # The preflight store contains the uploaded source and is a trusted stand-in
    # for the runner's output in this adapter test.
    import os

    root = Path(os.environ["QYUNSLATION_PREFLIGHT_ROOT"])
    preflight_file = root / preflight["storage_key"]
    fake = FakeService()
    monkeypatch.setattr(server_module, "get_translation_service", lambda: fake)

    created = client.post(
        "/api/v1/translation-runs",
        headers={**headers(), "Idempotency-Key": "completed-run"},
        json={"preflight_id": preflight["id"]},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "succeeded"
    assert len(body["artifacts"]) == 1
    artifact = body["artifacts"][0]
    assert artifact["filename"] == "protocol_translated.txt"
    assert artifact["download_url"].endswith(artifact["id"])

    downloaded = client.get(artifact["download_url"], headers=headers())
    assert downloaded.status_code == 200
    assert downloaded.content == b"translated clinical text"
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert client.get(artifact["download_url"], headers={"X-Dev-User": "other", "X-Dev-Tenant": "other"}).status_code == 404
