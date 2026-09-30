from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

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
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as test_client:
        yield test_client
    reset_engine()


def headers():
    return {"X-Dev-User": "planner", "X-Dev-Tenant": "pilot"}


def test_preflight_is_bounded_tenant_scoped_and_does_not_start_translation(client):
    response = client.post(
        "/api/v1/preflights",
        headers=headers(),
        data={"direction": "English → 简体中文", "profile": "临床研究文档"},
        files={"file": ("protocol.pdf", b"%PDF-1.7\nclinical", "application/pdf")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "ready"
    assert body["filename"] == "protocol.pdf"
    assert len(body["sha256"]) == 64
    assert body["capabilities"]["formal_export"] is False
    assert client.get(f"/api/v1/preflights/{body['id']}", headers=headers()).status_code == 200


def test_preflight_rejects_unsupported_format(client):
    response = client.post(
        "/api/v1/preflights",
        headers=headers(),
        files={"file": ("secrets.exe", b"not a document", "application/octet-stream")},
    )
    assert response.status_code == 415


def test_preferences_are_allowlisted_and_persisted(client):
    response = client.put(
        "/api/v1/preferences",
        headers=headers(),
        json={"preferences": {"density": "compact", "api_key": "must-not-persist"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["preferences"]["density"] == "compact"
    assert "api_key" not in body["preferences"]
    loaded = client.get("/api/v1/preferences", headers=headers())
    assert loaded.json()["preferences"]["density"] == "compact"


def test_plan066_migration_creates_new_tables(tmp_path, monkeypatch):
    database = tmp_path / "plan066.sqlite"
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", f"sqlite:///{database}")
    command.upgrade(Config("alembic.ini"), "head")
    inspector = inspect(create_engine(f"sqlite:///{database}"))
    tables = set(inspector.get_table_names())
    assert {"web_preference", "preflight_record"}.issubset(tables)
    command.downgrade(Config("alembic.ini"), "063a0001")
    downgraded = set(inspect(create_engine(f"sqlite:///{database}")).get_table_names())
    assert "web_preference" not in downgraded
    assert "preflight_record" not in downgraded
