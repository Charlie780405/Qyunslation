# SPDX-License-Identifier: MPL-2.0
"""PLAN-034g：审校入队 / 批准→TM / 术语候选 / diff / 审计。"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist import repo
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import AuditEvent, Base, Concept
from qyunslation.persist.review_repo import (
    decide_segment,
    enqueue_segments,
    should_enqueue,
)
from qyunslation.persist.tm_repo import lookup
from sqlalchemy import select


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
        try:
            s.commit()
        except Exception:
            s.rollback()
    finally:
        s.close()
        reset_engine()


@pytest.fixture()
def tenant_job(session):
    tenant = repo.get_or_create_tenant(session, slug="rv-tenant", name="Review")
    project = repo.create_project(session, tenant_id=tenant.id, slug="p1", name="P1")
    job = repo.create_job(session, project_id=project.id, source_sha256="c" * 64)
    session.commit()
    return tenant, project, job


def test_preserve_not_enqueued_human_review_is():
    assert should_enqueue("PRESERVE") is False
    assert should_enqueue("HUMAN_REVIEW") is True
    assert should_enqueue("TRANSLATE") is True
    assert should_enqueue("TERM_ONLY") is True


def test_enqueue_skips_preserve(session, tenant_job):
    tenant, _project, job = tenant_job
    created, skipped = enqueue_segments(
        session,
        job=job,
        items=[
            {
                "source_text": "Keep me",
                "machine_text": "",
                "policy": "PRESERVE",
                "block_id": "b0",
            },
            {
                "source_text": "Review me",
                "machine_text": "审我",
                "policy": "HUMAN_REVIEW",
                "block_id": "b1",
            },
        ],
    )
    session.commit()
    assert len(created) == 1
    assert created[0].policy == "HUMAN_REVIEW"
    assert any(s.get("reason") == "preserve" for s in skipped)
    _ = tenant


def test_unapproved_not_in_tm(session, tenant_job):
    tenant, project, job = tenant_job
    created, _ = enqueue_segments(
        session,
        job=job,
        items=[
            {
                "source_text": "Primary endpoint",
                "machine_text": "主要终点（机）",
                "policy": "HUMAN_REVIEW",
            }
        ],
    )
    session.commit()
    hit = lookup(session, tenant_id=tenant.id, source_text="Primary endpoint")
    assert hit["reuse"] is False
    # reject 仍不入库
    decide_segment(
        session,
        segment=created[0],
        tenant_id=tenant.id,
        actor_sub="r",
        action="reject",
    )
    session.commit()
    hit2 = lookup(session, tenant_id=tenant.id, source_text="Primary endpoint")
    assert hit2["reuse"] is False
    _ = project


def test_approve_writes_tm_and_reuse(session, tenant_job):
    tenant, project, job = tenant_job
    created, _ = enqueue_segments(
        session,
        job=job,
        items=[
            {
                "source_text": "Adverse event",
                "machine_text": "不良事件机译",
                "policy": "HUMAN_REVIEW",
            }
        ],
    )
    session.commit()
    out = decide_segment(
        session,
        segment=created[0],
        tenant_id=tenant.id,
        actor_sub="reviewer",
        action="approve",
        revised_text="不良事件",
        project_id=project.id,
    )
    session.commit()
    assert out["tm_unit_id"]
    hit = lookup(session, tenant_id=tenant.id, source_text="adverse event")
    assert hit["reuse"] is True
    assert hit["match"]["target_text"] == "不良事件"


def test_promote_term_staging(session, tenant_job):
    tenant, project, job = tenant_job
    created, _ = enqueue_segments(
        session,
        job=job,
        items=[
            {
                "source_text": "Novel Term XYZ",
                "machine_text": "新词",
                "policy": "TRANSLATE",
            }
        ],
    )
    session.commit()
    out = decide_segment(
        session,
        segment=created[0],
        tenant_id=tenant.id,
        actor_sub="r",
        action="approve",
        revised_text="新词XYZ",
        promote_term=True,
        project_id=project.id,
    )
    session.commit()
    assert out["concept_id"]
    c = session.get(Concept, out["concept_id"])
    assert c is not None
    assert c.status == "staging"


def test_diff_has_hunks(session, tenant_job):
    tenant, project, job = tenant_job
    created, _ = enqueue_segments(
        session,
        job=job,
        items=[
            {
                "source_text": "Dose 10 mg",
                "machine_text": "剂量 10 mg",
                "policy": "HUMAN_REVIEW",
            }
        ],
    )
    session.commit()
    decide_segment(
        session,
        segment=created[0],
        tenant_id=tenant.id,
        actor_sub="r",
        action="approve",
        revised_text="剂量为 10 mg",
        project_id=project.id,
    )
    session.commit()
    from qyunslation.persist.review_repo import diff_revisions

    d = diff_revisions(session, tenant_id=tenant.id, segment_id=created[0].id)
    assert d["a"] and d["b"]
    assert d["hunks"]


@pytest.fixture()
def client(monkeypatch):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(api_v1_router)
    with TestClient(app) as c:
        yield c
    reset_engine()


def test_api_review_loop_and_audit_strip(client):
    headers = {"X-Dev-User": "alice", "X-Dev-Tenant": "t-g"}
    proj = client.post(
        "/api/v1/projects",
        headers=headers,
        json={"slug": "rg", "name": "Review G"},
    )
    assert proj.status_code == 201
    pid = proj.json()["id"]
    job = client.post(
        "/api/v1/jobs",
        headers=headers,
        json={"project_id": pid, "source_sha256": "d" * 64},
    )
    assert job.status_code == 201
    jid = job.json()["id"]

    enq = client.post(
        "/api/v1/review/enqueue",
        headers=headers,
        json={
            "job_id": jid,
            "segments": [
                {
                    "source_text": "Refs block",
                    "machine_text": "不应入队",
                    "policy": "PRESERVE",
                },
                {
                    "source_text": "Study drug",
                    "machine_text": "试验药",
                    "policy": "HUMAN_REVIEW",
                },
            ],
        },
    )
    assert enq.status_code == 200
    body = enq.json()
    assert body["count"] == 1
    assert len(body["skipped"]) == 1
    sid = body["created"][0]["id"]

    note = client.post(
        f"/api/v1/review/segments/{sid}/note",
        headers=headers,
        json={"body": "请核对剂量"},
    )
    assert note.status_code == 201

    dec = client.post(
        f"/api/v1/review/segments/{sid}/decide",
        headers=headers,
        json={"action": "approve", "revised_text": "试验药物", "promote_term": True},
    )
    assert dec.status_code == 200
    assert dec.json()["tm_unit_id"]
    assert dec.json()["concept_id"]

    hit = client.post(
        "/api/v1/tm/lookup",
        headers=headers,
        json={"source_text": "study drug"},
    )
    assert hit.status_code == 200
    assert hit.json()["reuse"] is True

    diff = client.get(f"/api/v1/review/diff?segment_id={sid}", headers=headers)
    assert diff.status_code == 200
    assert diff.json()["hunks"]

    sug = client.get(
        "/api/v1/review/suggestions?source_text=study%20drug",
        headers=headers,
    )
    assert sug.status_code == 200
    assert sug.json()["tm"]["reuse"] is True

    # 审计表无密钥字段
    from qyunslation.persist.db import SessionLocal

    s = SessionLocal()
    try:
        events = list(s.scalars(select(AuditEvent)).all())
        assert any(e.action == "review.segment.approve" for e in events)
        for e in events:
            extra = e.extra or {}
            assert "api_key" not in extra
            assert "authorization" not in {k.lower() for k in extra}
    finally:
        s.close()


def test_review_html_does_not_interpolate_source_into_html():
    from pathlib import Path

    html = Path("qyunslation/static/review.html").read_text(encoding="utf-8")
    assert "textContent" in html
    assert "source_text || \"\"" in html or "source_text || '')" in html
    assert "innerHTML = `" not in html
    assert "${s.source_text" not in html
