# SPDX-License-Identifier: MPL-2.0
"""PLAN-058：ConceptTerm 向量旁路和语义降级。"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select

from qyunslation.persist import repo
from qyunslation.persist.concept_repo import create_staging_concept
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base, ConceptTermEmbedding
from qyunslation.persist.term_embedding_repo import (
    backfill_concept_term_embeddings,
    semantic_search_concept_terms,
)


@pytest.fixture()
def session():
    reset_engine()
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    from qyunslation.persist.db import SessionLocal

    assert SessionLocal is not None
    current = SessionLocal()
    try:
        yield current
    finally:
        current.close()
        reset_engine()


def test_backfill_and_semantic_search_are_project_scoped(session):
    tenant = repo.get_or_create_tenant(session, slug="embedding-tenant")
    project = repo.create_project(session, tenant_id=tenant.id, slug="p", name="P")
    concept = create_staging_concept(
        session,
        preferred_source="pharmacokinetic parameter",
        preferred_target="药代动力学参数",
        tenant_id=tenant.id,
        project_id=project.id,
    )
    concept.status = "curated"
    session.commit()

    vector = [1.0, 0.0, 0.0]
    with patch("qyunslation.embed.client.embed_texts", return_value=[vector, vector]):
        report = backfill_concept_term_embeddings(
            session, tenant_id=tenant.id, project_id=project.id, dim=3
        )
    assert report["created"] == 2
    assert session.scalars(select(ConceptTermEmbedding)).all()

    with patch("qyunslation.embed.client.embed_texts", return_value=[vector]):
        hits = semantic_search_concept_terms(
            session,
            tenant_id=tenant.id,
            project_id=project.id,
            query="PK parameter",
            src_lang="en",
            tgt_lang="zh",
            dim=3,
        )
    assert hits[0]["target_term"] == "药代动力学参数"
    assert hits[0]["project_id"] == project.id


def test_embedding_failure_degrades_without_fake_hit(session):
    tenant = repo.get_or_create_tenant(session, slug="embedding-down")
    with patch(
        "qyunslation.embed.client.embed_texts", side_effect=RuntimeError("offline")
    ):
        report = backfill_concept_term_embeddings(session, tenant_id=tenant.id)
    assert report["failed"] == 0
    with patch(
        "qyunslation.embed.client.embed_texts", side_effect=RuntimeError("offline")
    ):
        assert semantic_search_concept_terms(
            session,
            tenant_id=tenant.id,
            project_id=None,
            query="unknown",
            dim=3,
        ) == []
