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
        "print('Progress: 0.5, translate text', flush=True)\n"
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


def test_pdf_translation_run_uses_cli_state_and_authorized_artifact(client):
    preflight = client.post(
        "/api/v1/preflights",
        headers=_headers(),
        files={"file": ("protocol.pdf", b"%PDF-1.7", "application/pdf")},
    ).json()
    created = client.post(
        "/api/v1/translation-runs",
        headers={**_headers(), "Idempotency-Key": "pdf-run-once"},
        json={"preflight_id": preflight["id"]},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["external_task_id"].startswith("pdf2zh:")
    assert body["status"] in {"scanning", "translating", "rendering", "succeeded"}

    final = body
    for _ in range(30):
        time.sleep(0.05)
        final = client.get(f"/api/v1/translation-runs/{body['id']}", headers=_headers()).json()
        if final["status"] == "succeeded":
            break
    assert final["status"] == "succeeded"
    artifact = final["artifacts"][0]
    assert artifact["formal_export"] is True
    downloaded = client.get(artifact["download_url"], headers=_headers())
    assert downloaded.status_code == 200
    assert downloaded.content == b"%PDF fake translated"
    assert client.get(
        artifact["download_url"],
        headers={"X-Dev-User": "other", "X-Dev-Tenant": "other"},
    ).status_code == 404
