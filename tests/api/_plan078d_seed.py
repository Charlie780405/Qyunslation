"""Seed many runs directly in the database, for list/search/pagination/batch tests."""
from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from qyunslation.api import v1 as api_v1_module
from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist import db as persist_db
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base, PreflightRecord, Tenant, TranslationRunRecord

OWNER = {"X-Dev-User": "owner1", "X-Dev-Tenant": "pilot", "X-Dev-Role": "translator"}
OTHER = {"X-Dev-User": "other1", "X-Dev-Tenant": "pilot", "X-Dev-Role": "translator"}
REVIEWER = {"X-Dev-User": "rev1", "X-Dev-Tenant": "pilot", "X-Dev-Role": "reviewer"}
ADMIN = {"X-Dev-User": "adm1", "X-Dev-Tenant": "pilot", "X-Dev-Role": "system_admin"}
OTHER_TENANT = {"X-Dev-User": "owner1", "X-Dev-Tenant": "elsewhere", "X-Dev-Role": "translator"}

BASE_TIME = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
_counter = itertools.count(1)


def make_app(monkeypatch, tmp_path):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    monkeypatch.setenv("QYUNSLATION_PREFLIGHT_ROOT", str(tmp_path / "preflights"))
    monkeypatch.setenv("QYUNSLATION_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("QYUNSLATION_RUNNER_ROOT", str(tmp_path / "runs"))
    Base.metadata.create_all(init_engine("sqlite+pysqlite:///:memory:"))

    async def stub_launch(*, run, preflight, target_language, **kwargs):
        run.status = "failed"
        run.stage = "qa"

    monkeypatch.setattr(api_v1_module, "_launch_translation_run", stub_launch)
    app = FastAPI()
    app.include_router(api_v1_router)
    return TestClient(app)


def tenant_id(client, headers=OWNER) -> str:
    """Make sure the tenant (and the caller's membership) exist, then return its id."""
    client.get("/api/v1/translation-runs", headers=headers)
    with persist_db.SessionLocal() as session:
        slug = headers["X-Dev-Tenant"]
        return session.scalar(select(Tenant.id).where(Tenant.slug == slug))


def seed_run(
    session,
    tenant: str,
    *,
    name: str | None = None,
    filename: str = "doc.pdf",
    fmt: str | None = None,
    status: str = "gated",
    quality: str = "review_ready",
    direction: str = "English → 简体中文",
    domain: str = "general",
    created: datetime | None = None,
    updated: datetime | None = None,
    archived: bool = False,
    actor: str = "owner1",
    generation: int = 1,
    preflight: PreflightRecord | None = None,
    qa_summary: dict[str, Any] | None = None,
) -> TranslationRunRecord:
    n = next(_counter)
    created = created or BASE_TIME + timedelta(minutes=n)
    if preflight is None:
        preflight = PreflightRecord(
            tenant_id=tenant,
            actor_sub=actor,
            source_filename=filename,
            source_format=fmt or filename.rsplit(".", 1)[-1],
            source_sha256=f"{n:064x}",
            size_bytes=10,
            storage_key=f"{tenant}/seed-{n}",
            expires_at=created + timedelta(days=30),
        )
        session.add(preflight)
        session.flush()
    run = TranslationRunRecord(
        preflight_id=preflight.id,
        tenant_id=tenant,
        actor_sub=actor,
        idempotency_key_hash=f"{n:064x}",
        generation=generation,
        direction=direction,
        profile="临床研究文档",
        display_name=name,
        archived_at=created if archived else None,
        settings_snapshot={"domain_profile": domain, "source_language": "English", "target_language": "简体中文"},
        status=status,
        stage="review" if status == "gated" else "text",
        quality_state=quality,
        qa_summary=qa_summary or {"blocker": 0, "warning": 0, "info": 0},
        created_at=created,
        updated_at=updated or created,
    )
    session.add(run)
    session.flush()
    return run


def get_items(client, headers=OWNER, **params):
    response = client.get("/api/v1/translation-runs", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def collect_all(client, headers=OWNER, page_size=25, **params):
    """Walk every page with the returned cursor; returns the ids in order."""
    ids: list[str] = []
    cursor = None
    for _ in range(200):
        query = {**params, "page_size": page_size}
        if cursor:
            query["cursor"] = cursor
        page = get_items(client, headers, **query)
        ids.extend(item["id"] for item in page["items"])
        cursor = page.get("next_cursor")
        if not cursor:
            return ids
    raise AssertionError("pagination did not terminate")
