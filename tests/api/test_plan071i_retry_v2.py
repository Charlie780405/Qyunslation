# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import stat
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist import db as persist_db
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base, TranslationRunRecord


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
    monkeypatch.setenv("QYUNSLATION_PIPELINE", "legacy")
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


def test_retry_v2_creates_new_generation(client):
    preflight = client.post(
        "/api/v1/preflights",
        headers=_headers(),
        files={"file": ("protocol.pdf", b"%PDF-1.7", "application/pdf")},
    ).json()
    created = client.post(
        "/api/v1/translation-runs",
        headers={**_headers(), "Idempotency-Key": "retry-base"},
        json={"preflight_id": preflight["id"]},
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]
    assert persist_db.SessionLocal is not None
    with persist_db.SessionLocal() as session:
        run = session.scalar(select(TranslationRunRecord).where(TranslationRunRecord.id == run_id))
        assert run is not None
        run.status = "succeeded"
        run.quality_state = "legacy_unverified"
        run.generation = 1
        # Clear runner pointer so refresh cannot reopen a non-terminal status.
        run.external_task_id = None
        session.commit()
    retried = client.post(
        f"/api/v1/translation-runs/{run_id}/retry",
        headers=_headers(),
        json={"pipeline": "v2"},
    )
    assert retried.status_code == 201, retried.text
    body = retried.json()
    assert body["generation"] == 2
    assert body["id"] != run_id or body["generation"] == 2
    assert (body.get("settings") or {}).get("pipeline") == "v2"
    # Old generation untouched
    old = client.get(f"/api/v1/translation-runs/{run_id}", headers=_headers()).json()
    assert old["generation"] == 1
    assert old["quality_state"] == "legacy_unverified"
