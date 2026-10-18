"""PLAN-078 quick fixes: bilingual wiring, idempotency digest, preference persistence,
destructive-action authorization, delete ordering/audit, referenced-preflight guard."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from qyunslation.api import v1 as api_v1_module
from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import (
    AuditEvent,
    Base,
    ReviewDecision,
    TranslationRunRecord,
)
from qyunslation.workbench.runner import build_pdf2zh_command

OWNER = {"X-Dev-User": "owner1", "X-Dev-Tenant": "pilot", "X-Dev-Role": "translator"}
REVIEWER = {"X-Dev-User": "rev1", "X-Dev-Tenant": "pilot", "X-Dev-Role": "reviewer"}
ADMIN = {"X-Dev-User": "adm1", "X-Dev-Tenant": "pilot", "X-Dev-Role": "system_admin"}


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

    async def stub_launch(*, run, preflight, target_language, **kwargs):
        run.status = "failed"  # terminal so delete/archive paths are reachable
        run.stage = "qa"

    monkeypatch.setattr(api_v1_module, "_launch_translation_run", stub_launch)
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as current:
        yield current
    reset_engine()


def _preflight(client, headers=OWNER, name="doc.pdf", data=b"%PDF-1.7 a"):
    response = client.post(
        "/api/v1/preflights", headers=headers, files={"file": (name, data, "application/pdf")}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_run(client, preflight_id, key, headers=OWNER, **body):
    return client.post(
        "/api/v1/translation-runs",
        headers={**headers, "Idempotency-Key": key},
        json={"preflight_id": preflight_id, **body},
    )


# --- 1. bilingual option reaches the PDF executor ---------------------------------


def test_pdf_command_honours_bilingual_flag():
    base = dict(
        executable="pdf2zh_next",
        input_path=Path("/tmp/in.pdf"),
        output_dir=Path("/tmp/out"),
        direction="English → 简体中文",
    )
    assert "--no-dual" in build_pdf2zh_command(**base, settings={"bilingual": False})
    assert "--no-dual" not in build_pdf2zh_command(**base, settings={"bilingual": True})
    assert "--no-dual" not in build_pdf2zh_command(**base, settings={})


def test_snapshot_records_effective_bilingual(client):
    pdf = _preflight(client)
    run = _create_run(client, pdf["id"], "bi-pdf", bilingual=False).json()
    assert run["settings"]["bilingual"] is False
    assert run["settings"]["bilingual_effective"] is False
    docx = client.post(
        "/api/v1/preflights",
        headers=OWNER,
        files={"file": ("a.txt", b"hello world", "text/plain")},
    ).json()
    run2 = _create_run(client, docx["id"], "bi-txt", bilingual=True).json()
    # Non-PDF executors only emit the translation; the snapshot must say so.
    assert run2["settings"]["bilingual"] is True
    assert run2["settings"]["bilingual_effective"] is False


# --- 2. idempotency key is bound to the full configuration ------------------------


def test_same_key_same_config_returns_same_run(client):
    pdf = _preflight(client)
    first = _create_run(client, pdf["id"], "k1").json()
    again = _create_run(client, pdf["id"], "k1")
    assert again.status_code == 201
    assert again.json()["id"] == first["id"]


@pytest.mark.parametrize(
    "changed",
    [
        {"document_classification": "public"},
        {"bilingual": False},
        {"profile": "监管申报材料"},
        {"source_language": "简体中文", "target_language": "English"},
    ],
)
def test_same_key_different_config_is_rejected(client, changed):
    pdf = _preflight(client)
    assert _create_run(client, pdf["id"], "k2").status_code == 201
    response = _create_run(client, pdf["id"], "k2", **changed)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "IDEMPOTENCY_CONFIG_MISMATCH"


# --- 3. workbench preferences keep the model and AD document types ----------------


def test_preferences_round_trip_model_and_ad_profile(client):
    body = {
        "preferences": {
            "workbench": {
                "modelProfileId": "internal-qwen-quality",
                "profile": "医学研究文献",
                "domainProfile": "ad",
            }
        }
    }
    assert client.put("/api/v1/preferences", headers=OWNER, json=body).status_code == 200
    saved = client.get("/api/v1/preferences", headers=OWNER).json()["preferences"]["workbench"]
    assert saved["modelProfileId"] == "internal-qwen-quality"
    assert saved["profile"] == "医学研究文献"
    assert saved["domainProfile"] == "ad"


def test_preferences_reject_unknown_model(client):
    body = {"preferences": {"workbench": {"modelProfileId": "not-a-real-profile"}}}
    client.put("/api/v1/preferences", headers=OWNER, json=body)
    saved = client.get("/api/v1/preferences", headers=OWNER).json()["preferences"]["workbench"]
    assert saved["modelProfileId"] == "internal-qwen-quality"


# --- 4. destructive actions need ownership or an admin role -----------------------


def test_reviewer_cannot_delete_rename_restore_or_cancel_others_runs(client):
    pdf = _preflight(client)
    run_id = _create_run(client, pdf["id"], "own1").json()["id"]
    base = f"/api/v1/translation-runs/{run_id}"
    assert client.delete(base, headers=REVIEWER).status_code == 403
    assert client.patch(base, headers=REVIEWER, json={"display_name": "x"}).status_code == 403
    assert client.post(f"{base}/restore", headers=REVIEWER).status_code == 403
    assert client.post(f"{base}/cancel", headers=REVIEWER).status_code == 403
    # Reviewers still see the run (review work depends on it).
    assert client.get(base, headers=REVIEWER).status_code == 200
    assert client.get(base, headers=OWNER).status_code == 200


def test_owner_and_admin_can_delete(client):
    pdf = _preflight(client)
    mine = _create_run(client, pdf["id"], "own2").json()["id"]
    assert client.delete(f"/api/v1/translation-runs/{mine}", headers=OWNER).status_code == 204
    pdf2 = _preflight(client, name="b.pdf", data=b"%PDF-1.7 b")
    other = _create_run(client, pdf2["id"], "own3").json()["id"]
    assert client.delete(f"/api/v1/translation-runs/{other}", headers=ADMIN).status_code == 204


# --- 5. delete: commit first, unlink after, keep review evidence ------------------


def test_delete_commits_before_unlinking_and_audits_review_decisions(client, monkeypatch):
    from sqlalchemy.orm import Session

    pdf = _preflight(client)
    run_id = _create_run(client, pdf["id"], "del1").json()["id"]
    from qyunslation.persist.db import SessionLocal

    with SessionLocal() as session:
        run = session.get(TranslationRunRecord, run_id)
        session.add(
            ReviewDecision(
                run_id=run_id,
                generation=run.generation,
                decision="request_changes",
                user_id="rev1",
                comment="数字不一致",
                qa_snapshot={},
                term_snapshot={},
                model_snapshot={},
            )
        )
        session.commit()

    order: list[str] = []
    real_commit = Session.commit
    real_unlink = Path.unlink

    def spy_commit(self, *a, **k):
        order.append("commit")
        return real_commit(self, *a, **k)

    def spy_unlink(self, *a, **k):
        order.append("unlink")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Session, "commit", spy_commit)
    monkeypatch.setattr(Path, "unlink", spy_unlink)
    assert client.delete(f"/api/v1/translation-runs/{run_id}", headers=OWNER).status_code == 204
    assert "unlink" in order
    assert order.index("commit") < order.index("unlink")

    with SessionLocal() as session:
        audit = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "translation_run.delete")
        ).all()
        assert len(audit) == 1
        decisions = (audit[0].extra or {}).get("review_decisions")
        assert decisions and decisions[0]["decision"] == "request_changes"
        assert decisions[0]["comment"] == "数字不一致"


def test_failed_unlink_does_not_fail_or_resurrect_delete(client, monkeypatch):
    pdf = _preflight(client)
    run_id = _create_run(client, pdf["id"], "del2").json()["id"]

    def boom(self, *a, **k):
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "unlink", boom)
    assert client.delete(f"/api/v1/translation-runs/{run_id}", headers=OWNER).status_code == 204
    assert client.get(f"/api/v1/translation-runs/{run_id}", headers=OWNER).status_code == 404


# --- 6. referenced preflights cannot be deleted out from under their runs ---------


def test_delete_preflight_with_runs_is_conflict(client):
    pdf = _preflight(client)
    run_id = _create_run(client, pdf["id"], "pf1").json()["id"]
    response = client.delete(f"/api/v1/preflights/{pdf['id']}", headers=OWNER)
    assert response.status_code == 409
    assert client.get(f"/api/v1/translation-runs/{run_id}", headers=OWNER).status_code == 200
    unused = _preflight(client, name="c.pdf", data=b"%PDF-1.7 c")
    assert client.delete(f"/api/v1/preflights/{unused['id']}", headers=OWNER).status_code == 204
