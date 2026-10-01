# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base, TranslationRunRecord


@pytest.fixture()
def client(monkeypatch, tmp_path: Path):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as current:
        yield current
    reset_engine()


def _admin_headers():
    return {"X-Dev-User": "admin", "X-Dev-Tenant": "pilot", "X-Dev-Role": "admin"}


def test_egress_audit_lists_runs_with_external_scope(client, monkeypatch):
    from qyunslation.persist import repo
    from qyunslation.persist.db import SessionLocal

    assert SessionLocal is not None
    with SessionLocal() as session:
        tenant = repo.get_or_create_tenant(session, slug="pilot")
        run = TranslationRunRecord(
            tenant_id=tenant.id,
            actor_sub="admin",
            preflight_id="00000000-0000-0000-0000-000000000001",
            idempotency_key_hash="egress-test",
            direction="English → 简体中文",
            profile="临床研究文档",
            settings_snapshot={
                "model_snapshot": {
                    "egress_scope": "full_document",
                    "provider": "deepseek",
                    "model_id": "deepseek-chat",
                }
            },
            status="translating",
            stage="text",
            term_summary={"egress_fragment_count": 12},
        )
        session.add(run)
        session.commit()

    response = client.get("/api/v1/admin/egress-audit", headers=_admin_headers())
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["egress_scope"] == "full_document"
    assert items[0]["fragment_count"] == 12
