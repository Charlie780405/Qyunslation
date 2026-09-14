# SPDX-License-Identifier: MPL-2.0
"""PLAN-055：TM 语义建议（mock embed，reuse 仅精确）。"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from qyunslation.persist import repo
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base, TmUnit, TmUnitEmbedding
from qyunslation.persist.tm_repo import (
    cosine_similarity,
    create_approved_unit,
    lookup,
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
    return repo.get_or_create_tenant(session, slug="tm-sem", name="TM Semantic")


def test_cosine_identical():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_exact_reuse_skips_semantic(session, tenant):
    with patch("qyunslation.embed.client.embed_texts", return_value=[[1.0, 0.0, 0.0, 0.0]]):
        create_approved_unit(
            session,
            tenant_id=tenant.id,
            source_text="Primary endpoint is PASI 75",
            target_text="主要终点为 PASI 75",
            approved=True,
            approved_by="tester",
        )
    got = lookup(
        session,
        tenant_id=tenant.id,
        source_text="Primary endpoint is PASI 75",
    )
    assert got["reuse"] is True
    assert got["semantic_suggestions"] == []


def test_semantic_suggestions_not_reuse(session, tenant):
    # 手工插入 unit + embedding，避免 create 时真实 embed
    unit = TmUnit(
        tenant_id=tenant.id,
        project_id=None,
        src_lang="en",
        tgt_lang="zh",
        source_text="Patients received subcutaneous injection",
        target_text="患者接受皮下注射",
        source_norm="patients received subcutaneous injection",
        placeholder_sig="",
        approved=True,
        approved_by="t",
        approved_at=datetime.now(timezone.utc),
        version=1,
    )
    session.add(unit)
    session.flush()
    session.add(
        TmUnitEmbedding(
            unit_id=unit.id,
            dim=4,
            model="bge-m3",
            vector=[1.0, 0.0, 0.0, 0.0],
            created_at=datetime.now(timezone.utc),
        )
    )
    session.flush()

    with patch(
        "qyunslation.embed.client.embed_texts",
        return_value=[[0.99, 0.01, 0.0, 0.0]],
    ):
        got = lookup(
            session,
            tenant_id=tenant.id,
            source_text="Subjects were given a subcutaneous shot",
            semantic_threshold=0.5,
            semantic_limit=5,
        )
    assert got["reuse"] is False
    assert got["match"] is None
    assert len(got["semantic_suggestions"]) >= 1
    assert got["semantic_suggestions"][0]["kind"] == "semantic"
    assert got["semantic_suggestions"][0]["unit_id"] == unit.id


def test_semantic_embed_failure_degrades(session, tenant):
    unit = TmUnit(
        tenant_id=tenant.id,
        project_id=None,
        src_lang="en",
        tgt_lang="zh",
        source_text="Hello world clinical trial",
        target_text="你好世界临床试验",
        source_norm="hello world clinical trial",
        placeholder_sig="",
        approved=True,
        approved_by="t",
        approved_at=datetime.now(timezone.utc),
        version=1,
    )
    session.add(unit)
    session.flush()
    with patch(
        "qyunslation.embed.client.embed_texts",
        side_effect=RuntimeError("down"),
    ):
        got = lookup(
            session,
            tenant_id=tenant.id,
            source_text="Hello world study",
            fuzzy_threshold=0.3,
        )
    assert got["reuse"] is False
    assert got["semantic_suggestions"] == []
