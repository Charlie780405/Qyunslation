# SPDX-License-Identifier: MPL-2.0
"""PLAN-034d：Concept 导入 / 扁平化 / staging 门禁 / forbidden。"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.api.v1 import router as api_v1_router
from qyunslation.glossary.concept_flatten import flatten_curated_dict
from qyunslation.glossary.governance import build_merged_dict, load_curated_entries
from qyunslation.persist.concept_repo import (
    count_by_status,
    create_staging_concept,
    detect_forbidden,
    list_forbidden_texts,
    upsert_curated_from_entry,
)
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base


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


def test_import_csv_idempotent_and_flatten(session):
    entries = load_curated_entries()
    assert len(entries) >= 100
    for e in entries:
        upsert_curated_from_entry(session, e)
    session.commit()
    n1 = count_by_status(session, "curated")
    for e in entries:
        upsert_curated_from_entry(session, e)
    session.commit()
    n2 = count_by_status(session, "curated")
    assert n1 == n2
    assert n1 >= 100
    # 同 normalize key 可能合并，故 concepts ≤ CSV 行数
    assert n1 <= len(entries)

    flat = flatten_curated_dict(session)
    assert flat
    assert flat.get("景行生物") == "GenScend"
    # build_merged_dict 在引擎就绪时走 DB
    csv_flat = build_merged_dict()
    assert csv_flat.get("景行生物") == "GenScend"
    assert abs(len(flat) - len(csv_flat)) <= 5


def test_staging_does_not_pollute_curated(session):
    entries = load_curated_entries()[:5]
    for e in entries:
        upsert_curated_from_entry(session, e)
    session.commit()
    curated_before = count_by_status(session, "curated")
    create_staging_concept(
        session,
        preferred_source="LLM Candidate Term XYZ",
        preferred_target="候选词",
        layer="harvest",
    )
    session.commit()
    assert count_by_status(session, "curated") == curated_before
    assert count_by_status(session, "staging") == 1
    flat = flatten_curated_dict(session)
    assert "LLM Candidate Term XYZ" not in flat


def test_detect_forbidden_pure():
    assert detect_forbidden("使用错误译法foo", ["foo"]) is True
    assert detect_forbidden("干净译文", ["foo"]) is False
    assert detect_forbidden("", ["foo"]) is False


def test_forbidden_from_db(session):
    c = create_staging_concept(
        session,
        preferred_source="drug",
        preferred_target="药品",
        forbidden=[("zh", "假药译法")],
    )
    # staging 默认不进 curated forbidden 列表
    assert list_forbidden_texts(session, curated_only=True) == []
    c.status = "curated"
    session.commit()
    hits = list_forbidden_texts(session, curated_only=True)
    assert "假药译法" in hits
    assert detect_forbidden("含假药译法的句子", hits) is True


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


def test_api_create_forces_staging(client):
    headers = {"X-Dev-User": "alice", "X-Dev-Tenant": "t1"}
    r = client.post(
        "/api/v1/concepts",
        json={
            "preferred_source": "foo",
            "preferred_target": "某某",
            "status": "curated",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "staging"
    assert body["tenant_id"]
    listed = client.get("/api/v1/concepts?status=staging", headers=headers)
    assert listed.status_code == 200
    assert any(x["id"] == body["id"] for x in listed.json())


def test_api_concepts_are_tenant_scoped(client):
    a = {"X-Dev-User": "alice", "X-Dev-Tenant": "tenant-a"}
    b = {"X-Dev-User": "bob", "X-Dev-Tenant": "tenant-b"}
    created = client.post(
        "/api/v1/concepts",
        json={"preferred_source": "secret-term", "preferred_target": "密词"},
        headers=a,
    )
    assert created.status_code == 201
    cid = created.json()["id"]
    listed_a = client.get("/api/v1/concepts?status=staging", headers=a)
    listed_b = client.get("/api/v1/concepts?status=staging", headers=b)
    assert any(x["id"] == cid for x in listed_a.json())
    assert all(x["id"] != cid for x in listed_b.json())


def test_csv_fallback_without_engine():
    reset_engine()
    d = build_merged_dict()
    assert len(d) >= 100
    assert d.get("景行生物") == "GenScend"
