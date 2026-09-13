# SPDX-License-Identifier: MPL-2.0
"""PLAN-034e：TM 批准门禁 / 精确+签名 / 模糊不 reuse / TMX round-trip。"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qyunslation.api.v1 import router as api_v1_router
from qyunslation.persist import repo
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base, TmUnit
from qyunslation.persist.tm_repo import (
    ApprovalRequiredError,
    create_approved_unit,
    lookup,
    stage_import_unit,
)
from qyunslation.tm.match import exact_lookup, fuzzy_suggest
from qyunslation.tm.normalize import normalize_source, placeholder_signature
from qyunslation.tm.tmx import (
    MAX_LANG_LEN,
    MAX_TMX_BYTES,
    TmxRejected,
    build_tmx,
    parse_tmx,
)


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
def tenant(session):
    return repo.get_or_create_tenant(session, slug="tm-tenant", name="TM Tenant")


def test_tmx_rejects_entity_expansion():
    """xml.etree 会展开内部实体（十亿笑），必须在解析前拒掉。"""
    bomb = (
        '<?xml version="1.0"?>\n'
        "<!DOCTYPE tmx [\n"
        '  <!ENTITY a "AAAAAAAAAA">\n'
        '  <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">\n'
        "]>\n"
        '<tmx version="1.4"><body><tu>'
        '<tuv xml:lang="en"><seg>&b;</seg></tuv>'
        '<tuv xml:lang="zh"><seg>x</seg></tuv>'
        "</tu></body></tmx>"
    )
    with pytest.raises(TmxRejected):
        parse_tmx(bomb)


def test_tmx_rejects_overlong_lang():
    """超长 xml:lang 会溢出 TmUnit.src_lang 的 String(16)，须在解析层拦。"""
    bad = (
        '<tmx version="1.4"><body><tu>'
        f'<tuv xml:lang="{"e" * (MAX_LANG_LEN + 4)}"><seg>a</seg></tuv>'
        '<tuv xml:lang="zh"><seg>b</seg></tuv>'
        "</tu></body></tmx>"
    )
    with pytest.raises(TmxRejected):
        parse_tmx(bad)


def test_tmx_rejects_oversize_payload():
    with pytest.raises(TmxRejected):
        parse_tmx("x" * (MAX_TMX_BYTES + 1))


def test_normalize_and_signature():
    assert normalize_source("  Hello   WORLD ") == "hello world"
    sig_a = placeholder_signature("Dose 10 mg at 50%")
    sig_b = placeholder_signature("Dose 20 mg at 25%")
    assert "NUM" in sig_a
    assert sig_a == sig_b  # 结构签名一致，数值不同仍同型
    sig_c = placeholder_signature("See https://example.com/a")
    assert "URL" in sig_c
    assert sig_a != sig_c


def test_unapproved_rejected(session, tenant):
    with pytest.raises(ApprovalRequiredError):
        create_approved_unit(
            session,
            tenant_id=tenant.id,
            source_text="Hello",
            target_text="你好",
            approved=False,
        )


def test_exact_and_signature_gate(session, tenant):
    create_approved_unit(
        session,
        tenant_id=tenant.id,
        source_text="Dose of 10 mg",
        target_text="剂量 10 mg",
        approved=True,
        approved_by="reviewer",
    )
    session.commit()
    hit = lookup(session, tenant_id=tenant.id, source_text="dose of 10 mg")
    assert hit["reuse"] is True
    assert hit["match"]["target_text"] == "剂量 10 mg"

    # 源文不同 → 不精确复用（即使签名类型可能相近）
    miss = lookup(session, tenant_id=tenant.id, source_text="Dose of 20 mg")
    assert miss["reuse"] is False

    # 签名变：加入 URL 后 placeholder_sig 变化 → 不复用
    create_approved_unit(
        session,
        tenant_id=tenant.id,
        source_text="Visit https://a.example/x for info",
        target_text="访问链接了解信息",
        approved=True,
        approved_by="reviewer",
    )
    session.commit()
    same_text_diff_sig = lookup(
        session,
        tenant_id=tenant.id,
        source_text="Visit https://b.example/y for info",
    )
    # 规范化文本不同（URL 字面不同）→ reuse false
    assert same_text_diff_sig["reuse"] is False


def test_signature_mismatch_blocks_reuse_when_norm_equal():
    """同 norm 但签名不同时 exact_lookup 拒绝。"""

    class U:
        id = "1"
        source_text = "x"
        target_text = "y"
        source_norm = "hello"
        placeholder_sig = "NUM"

    assert exact_lookup("hello", [U()], query_norm="hello", query_sig="NUM") is not None
    assert exact_lookup("hello", [U()], query_norm="hello", query_sig="URL") is None


def test_fuzzy_suggestions_not_reuse(session, tenant):
    create_approved_unit(
        session,
        tenant_id=tenant.id,
        source_text="Adverse event was reported",
        target_text="报告了不良事件",
        approved=True,
        approved_by="r",
    )
    session.commit()
    result = lookup(
        session,
        tenant_id=tenant.id,
        source_text="Adverse events were reported",
        fuzzy_threshold=0.85,
    )
    assert result["reuse"] is False
    assert result["match"] is None
    assert result["suggestions"]
    assert all("target_text" in s for s in result["suggestions"])

    from sqlalchemy import select

    units = list(session.scalars(select(TmUnit).where(TmUnit.approved.is_(True))).all())
    sug = fuzzy_suggest(
        "Adverse events were reported",
        units,
        threshold=0.85,
    )
    assert sug
    assert sug[0].score >= 0.85


def test_tmx_round_trip(session, tenant):
    create_approved_unit(
        session,
        tenant_id=tenant.id,
        source_text="Adverse event",
        target_text="不良事件",
        approved=True,
        approved_by="r",
    )
    session.commit()
    from qyunslation.persist.tm_repo import list_approved_units

    approved = list_approved_units(session, tenant_id=tenant.id)
    xml = build_tmx(approved, src_lang="en", tgt_lang="zh")
    assert "<tu>" in xml and "<seg>" in xml
    parsed = parse_tmx(xml)
    assert len(parsed) == 1
    assert parsed[0].source_text == "Adverse event"
    assert parsed[0].target_text == "不良事件"

    # 导入默认未批准
    staged = stage_import_unit(
        session,
        tenant_id=tenant.id,
        source_text=parsed[0].source_text,
        target_text=parsed[0].target_text,
        src_lang=parsed[0].src_lang,
        tgt_lang=parsed[0].tgt_lang,
    )
    assert staged.approved is False
    # 未批准不进 lookup 池
    again = lookup(session, tenant_id=tenant.id, source_text="Adverse event")
    assert again["reuse"] is True  # 仍命中已批准那条


def test_api_approve_gate_and_lookup(monkeypatch):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QYUNSLATION_DEV_AUTH_BYPASS", "1")
    monkeypatch.setenv("QYUNSLATION_ENV", "development")
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(api_v1_router)
    headers = {"X-Dev-User": "u1", "X-Dev-Tenant": "tm-tenant"}
    with TestClient(app) as client:
        forbidden = client.post(
            "/api/v1/tm/units",
            headers=headers,
            json={
                "source_text": "Primary endpoint",
                "target_text": "主要终点",
                "approved": True,
            },
        )
        assert forbidden.status_code == 400

        staged = client.post(
            "/api/v1/tm/units",
            headers=headers,
            json={"source_text": "Primary endpoint", "target_text": "主要终点"},
        )
        assert staged.status_code == 201
        assert staged.json()["approved"] is False

        miss = client.post(
            "/api/v1/tm/lookup",
            headers=headers,
            json={"source_text": "primary endpoint"},
        )
        assert miss.status_code == 200
        assert miss.json()["reuse"] is False

        proj = client.post(
            "/api/v1/projects",
            headers=headers,
            json={"slug": "tm", "name": "TM"},
        )
        jid = client.post(
            "/api/v1/jobs",
            headers=headers,
            json={"project_id": proj.json()["id"], "source_sha256": "a" * 64},
        ).json()["id"]
        enq = client.post(
            "/api/v1/review/enqueue",
            headers=headers,
            json={
                "job_id": jid,
                "segments": [
                    {
                        "source_text": "Primary endpoint",
                        "machine_text": "主要终点",
                        "policy": "HUMAN_REVIEW",
                    }
                ],
            },
        )
        sid = enq.json()["created"][0]["id"]
        decided = client.post(
            f"/api/v1/review/segments/{sid}/decide",
            headers=headers,
            json={"action": "approve", "revised_text": "主要终点"},
        )
        assert decided.status_code == 200

        hit = client.post(
            "/api/v1/tm/lookup",
            headers=headers,
            json={"source_text": "primary endpoint"},
        )
        assert hit.status_code == 200
        body = hit.json()
        assert body["reuse"] is True
        assert body["match"]["target_text"] == "主要终点"

        exported = client.get("/api/v1/tm/export.tmx", headers=headers)
        assert exported.status_code == 200
        assert "主要终点" in exported.text

        imp = client.post(
            "/api/v1/tm/import.tmx",
            headers=headers,
            json={"tmx": exported.text},
        )
        assert imp.status_code == 200
        assert imp.json()["imported"] >= 1
        assert all(u["approved"] is False for u in imp.json()["units"])
    reset_engine()
