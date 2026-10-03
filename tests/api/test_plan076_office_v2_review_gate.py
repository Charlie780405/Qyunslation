"""PLAN-076 pilot regression: office (non-PDF) executor under pipeline v2.

Before the fix a docx/txt run reached ``download_ready`` and was parked at
``translating/layout`` forever: auto QA never ran, ``review_ready`` was never
reached, and approving re-parked the run instead of materialising artifacts.
"""
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
    monkeypatch.setenv("QYUNSLATION_PIPELINE", "v2")
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


def _headers(user: str = "planner"):
    return {"X-Dev-User": user, "X-Dev-Tenant": "pilot"}


def test_office_v2_run_reaches_review_ready_and_materialises_after_approval(client, monkeypatch, tmp_path):
    output = tmp_path / "protocol_translated.txt"
    output.write_text("临床文本译文", encoding="utf-8")
    from qyunslation import server as server_module

    class FakeService:
        main_event_loop = object()

        async def start_translation(self, **kwargs):
            return {"task_id": "office-task"}

        def get_task_state(self, task_id):
            assert task_id == "office-task"
            return {
                "download_ready": True,
                "is_processing": False,
                "error_flag": False,
                "status_message": "翻译完成！用时 1.00 秒。",
                "original_filename": "protocol.txt",
                "downloadable_files": {"txt": {"path": str(output), "filename": output.name}},
                "attachment_files": {},
            }

        def cancel_task(self, task_id):
            return {"cancelled": True}

    monkeypatch.setattr(server_module, "get_translation_service", lambda: FakeService())

    preflight = client.post(
        "/api/v1/preflights",
        headers=_headers(),
        files={"file": ("protocol.txt", b"clinical text", "text/plain")},
    ).json()
    created = client.post(
        "/api/v1/translation-runs",
        headers={**_headers(), "Idempotency-Key": "office-v2"},
        json={"preflight_id": preflight["id"], "direction": "English → 简体中文", "profile": "临床研究文档"},
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]

    detail = client.get(f"/api/v1/translation-runs/{run_id}", headers=_headers()).json()
    assert detail["settings"]["pipeline"] == "v2"
    assert detail["quality_state"] == "review_ready", detail
    assert detail["stage"] == "review"
    assert detail["status"] == "translating"
    assert detail["artifacts"] == []

    # Polling again must be idempotent: no second QA pass, no duplicated events.
    events_url = f"/api/v1/translation-runs/{run_id}/events?after_sequence=0"
    first_events = client.get(events_url, headers=_headers()).json()["items"]
    for _ in range(3):
        client.get(f"/api/v1/translation-runs/{run_id}", headers=_headers())
    again = client.get(events_url, headers=_headers()).json()["items"]
    assert len(again) == len(first_events), [e.get("message") for e in again[len(first_events):]]

    approved = client.post(
        f"/api/v1/translation-runs/{run_id}/review-decision",
        headers={**_headers(), "X-Dev-Role": "reviewer"},
        json={"decision": "approve"},
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["quality_state"] == "approved"
    assert body["status"] == "succeeded"
    assert body["stage"] == "export"
    formal = [item for item in body["artifacts"] if item["formal_export"]]
    assert len(formal) == 1
    downloaded = client.get(formal[0]["download_url"], headers=_headers())
    assert downloaded.status_code == 200
    assert downloaded.content.decode("utf-8") == "临床文本译文"


def test_office_v2_reject_is_terminal_and_retry_allocates_new_generation(client, monkeypatch, tmp_path):
    output = tmp_path / "protocol_translated.txt"
    output.write_text("译文", encoding="utf-8")
    from qyunslation import server as server_module

    class FakeService:
        main_event_loop = object()

        async def start_translation(self, **kwargs):
            return {"task_id": "office-task-2"}

        def get_task_state(self, task_id):
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
    preflight = client.post(
        "/api/v1/preflights",
        headers=_headers(),
        files={"file": ("protocol.txt", b"clinical text", "text/plain")},
    ).json()
    run_id = client.post(
        "/api/v1/translation-runs",
        headers={**_headers(), "Idempotency-Key": "office-v2-reject"},
        json={"preflight_id": preflight["id"], "direction": "English → 简体中文", "profile": "临床研究文档"},
    ).json()["id"]
    assert client.get(f"/api/v1/translation-runs/{run_id}", headers=_headers()).json()["quality_state"] == "review_ready"

    rejected = client.post(
        f"/api/v1/translation-runs/{run_id}/review-decision",
        headers={**_headers(), "X-Dev-Role": "reviewer"},
        json={"decision": "reject", "comment": "number omitted"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "failed"
    # The executor's lingering download_ready state must not revive the run.
    again = client.get(f"/api/v1/translation-runs/{run_id}", headers=_headers()).json()
    assert again["status"] == "failed"
    retried = client.post(f"/api/v1/translation-runs/{run_id}/retry", headers=_headers())
    assert retried.status_code == 201, retried.text
    assert retried.json()["generation"] == 2
    assert retried.json()["id"] != run_id


def test_ad_retry_carries_frozen_prompt_into_next_generation(client, monkeypatch, tmp_path):
    monkeypatch.setenv("QYUNSLATION_AD_PROMPT_TENANTS", "pilot")
    output = tmp_path / "ad_translated.txt"
    output.write_text("特应性皮炎患者接受度普利尤单抗治疗。", encoding="utf-8")
    from qyunslation import server as server_module

    class FakeService:
        main_event_loop = object()

        async def start_translation(self, **kwargs):
            return {"task_id": "office-task-ad"}

        def get_task_state(self, task_id):
            return {
                "download_ready": True,
                "is_processing": False,
                "error_flag": False,
                "original_filename": "ad.txt",
                "downloadable_files": {"txt": {"path": str(output), "filename": output.name}},
                "attachment_files": {},
            }

        def cancel_task(self, task_id):
            return {"cancelled": True}

    monkeypatch.setattr(server_module, "get_translation_service", lambda: FakeService())
    preflight = client.post(
        "/api/v1/preflights",
        headers=_headers(),
        files={"file": ("ad.txt", b"Patients with atopic dermatitis received dupilumab.", "text/plain")},
    ).json()
    created = client.post(
        "/api/v1/translation-runs",
        headers={**_headers(), "Idempotency-Key": "ad-retry"},
        json={"preflight_id": preflight["id"], "domain_profile": "ad", "direction": "English → 简体中文", "profile": "医学研究文献"},
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]
    digest = created.json()["prompt_snapshot"]["digest"]
    assert client.get(f"/api/v1/translation-runs/{run_id}", headers=_headers()).json()["status"] != "blocked"

    client.post(
        f"/api/v1/translation-runs/{run_id}/review-decision",
        headers={**_headers(), "X-Dev-Role": "reviewer"},
        json={"decision": "reject", "comment": "retranslate"},
    )
    retried = client.post(f"/api/v1/translation-runs/{run_id}/retry", headers=_headers())
    assert retried.status_code == 201, retried.text
    body = retried.json()
    assert body["generation"] == 2
    assert body["status"] != "blocked", body.get("degradation_reason")
    assert body["prompt_snapshot"]["digest"] == digest
