# SPDX-License-Identifier: MPL-2.0
"""PLAN-034c：persist CRUD / 审计 / 身份旁路。"""
from __future__ import annotations

import os

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from qyunslation.persist.audit import record_audit, sanitize_extra
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.identity import DevBypassAdapter, resolve_identity
from qyunslation.persist.models import AuditEvent, Base
from qyunslation.persist import repo


@pytest.fixture()
def session():
    reset_engine()
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    from qyunslation.persist.db import SessionLocal

    assert SessionLocal is not None
    s = SessionLocal()
    try:
        yield s
        s.commit()
    finally:
        s.close()
        reset_engine()


def test_project_job_crud(session):
    tenant = repo.get_or_create_tenant(session, slug="acme", name="Acme")
    repo.ensure_membership(session, tenant_id=tenant.id, user_sub="u1", role="admin")
    project = repo.create_project(session, tenant_id=tenant.id, slug="p1", name="Proj")
    digest = "a" * 64
    job = repo.create_job(
        session, project_id=project.id, source_sha256=digest, storage_key="obj/a.pdf"
    )
    assert repo.get_project(session, project_id=project.id, tenant_id=tenant.id) is not None
    assert repo.get_job(session, job_id=job.id).source_sha256 == digest
    assert len(repo.list_jobs(session, project_id=project.id)) == 1


def test_membership_promotes_explicit_provider_role_without_downgrade(session):
    tenant = repo.get_or_create_tenant(session, slug="roles")
    membership = repo.ensure_membership(session, tenant_id=tenant.id, user_sub="u1", role="reviewer")
    assert membership.role == "reviewer"
    promoted = repo.ensure_membership(session, tenant_id=tenant.id, user_sub="u1", role="term_admin")
    assert promoted.role == "term_admin"
    preserved = repo.ensure_membership(session, tenant_id=tenant.id, user_sub="u1", role="member")
    assert preserved.role == "term_admin"


def test_audit_strips_secrets(session):
    assert sanitize_extra({"authorization": "Bearer x", "ok": 1}) == {"ok": 1}
    event = record_audit(
        session,
        actor_sub="u1",
        action="job.create",
        source_sha256="b" * 64,
        extra={"api_key": "secret", "job_id": "j1", "token": "t"},
    )
    session.commit()
    loaded = session.get(AuditEvent, event.id)
    assert loaded is not None
    assert loaded.extra == {"job_id": "j1"}
    assert "api_key" not in (loaded.extra or {})


def test_production_rejects_dev_bypass(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_ENV", "production")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"",
    }
    request = Request(scope)
    with pytest.raises(HTTPException) as exc:
        DevBypassAdapter().resolve(request)
    assert exc.value.status_code == 403


def test_dev_bypass_requires_flag(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    monkeypatch.delenv("QYUNSLATION_DEV_AUTH_BYPASS", raising=False)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"",
    }
    request = Request(scope)
    with pytest.raises(HTTPException) as exc:
        resolve_identity(request)
    assert exc.value.status_code in {401, 501, 503}
