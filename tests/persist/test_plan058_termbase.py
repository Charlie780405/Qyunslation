from __future__ import annotations

import pytest

from qyunslation.glossary.termbase import list_runtime_terms, resolve_runtime_terms
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import (
    Base,
    Concept,
    ConceptTerm,
    Job,
    Project,
    Tenant,
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
        current.commit()
    finally:
        current.close()
        reset_engine()


def test_runtime_terms_are_project_scoped_and_project_wins_clinical(session):
    tenant = Tenant(slug="tenant-058", name="Tenant 058")
    session.add(tenant)
    session.flush()
    project = Project(tenant_id=tenant.id, slug="p-058", name="Project 058")
    other_project = Project(tenant_id=tenant.id, slug="other", name="Other")
    session.add_all([project, other_project])
    session.flush()

    clinical = Concept(
        tenant_id=None,
        project_id=None,
        status="curated",
        layer="clinical",
        domain="clinical",
        term_type="endpoint",
    )
    project_term = Concept(
        tenant_id=tenant.id,
        project_id=project.id,
        status="curated",
        layer="project",
        domain="clinical",
        term_type="endpoint",
    )
    other_term = Concept(
        tenant_id=tenant.id,
        project_id=other_project.id,
        status="curated",
        layer="project",
        domain="clinical",
        term_type="endpoint",
    )
    session.add_all([clinical, project_term, other_term])
    session.flush()
    session.add_all(
        [
            ConceptTerm(concept_id=clinical.id, lang="en", text="primary endpoint", role="preferred"),
            ConceptTerm(concept_id=clinical.id, lang="zh", text="主要终点", role="preferred"),
            ConceptTerm(concept_id=project_term.id, lang="en", text="primary endpoint", role="preferred"),
            ConceptTerm(concept_id=project_term.id, lang="zh", text="主要疗效终点", role="preferred"),
            ConceptTerm(concept_id=other_term.id, lang="en", text="primary endpoint", role="preferred"),
            ConceptTerm(concept_id=other_term.id, lang="zh", text="其他项目终点", role="preferred"),
        ]
    )
    session.commit()

    records = list_runtime_terms(
        session,
        tenant_id=tenant.id,
        project_id=project.id,
        src_lang="en",
        tgt_lang="zh",
    )

    assert [(record.concept_id, record.target_term) for record in records] == [
        (project_term.id, "主要疗效终点")
    ]


def test_runtime_terms_normalize_human_language_names(session):
    tenant = Tenant(slug="tenant-058-lang", name="Tenant 058 language")
    session.add(tenant)
    session.flush()
    project = Project(tenant_id=tenant.id, slug="p", name="P")
    session.add(project)
    session.flush()
    concept = Concept(
        tenant_id=tenant.id,
        project_id=project.id,
        status="curated",
        layer="project",
        domain="clinical",
    )
    session.add(concept)
    session.flush()
    session.add_all(
        [
            ConceptTerm(concept_id=concept.id, lang="en", text="endpoint", role="preferred"),
            ConceptTerm(concept_id=concept.id, lang="zh", text="终点", role="preferred"),
        ]
    )
    session.commit()

    matches = resolve_runtime_terms(
        session,
        tenant_id=tenant.id,
        project_id=project.id,
        text="endpoint",
        src_lang="English",
        tgt_lang="Simplified Chinese",
    )
    assert matches[0].target_term == "终点"


def test_resolve_runtime_terms_uses_exact_path_without_embedding(session, monkeypatch):
    tenant = Tenant(slug="tenant-058b", name="Tenant 058b")
    session.add(tenant)
    session.flush()
    project = Project(tenant_id=tenant.id, slug="p", name="P")
    session.add(project)
    session.flush()
    concept = Concept(
        tenant_id=tenant.id,
        project_id=project.id,
        status="curated",
        layer="project",
        domain="clinical",
        term_type="drug",
    )
    session.add(concept)
    session.flush()
    session.add_all(
        [
            ConceptTerm(concept_id=concept.id, lang="en", text="tralokinumab", role="preferred"),
            ConceptTerm(concept_id=concept.id, lang="zh", text="tralokinumab", role="preferred"),
        ]
    )
    session.commit()

    def fail_embedding(*args, **kwargs):
        raise AssertionError("exact term resolution must not call embedding")

    monkeypatch.setattr("qyunslation.embed.client.embed_texts", fail_embedding)
    result = resolve_runtime_terms(
        session,
        tenant_id=tenant.id,
        project_id=project.id,
        text="Patients received tralokinumab.",
        src_lang="en",
        tgt_lang="zh",
    )

    assert len(result) == 1
    assert result[0].target_term == "tralokinumab"
    assert result[0].match_type == "exact"
