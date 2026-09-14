from __future__ import annotations

import pytest
from sqlalchemy import select

from qyunslation.persist.candidate_repo import (
    CandidateConflict,
    decide_candidate,
    enqueue_candidate,
    list_candidates,
)
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import (
    Base,
    Concept,
    ConceptTerm,
    DocumentTermCandidate,
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
    finally:
        current.close()
        reset_engine()


def _job(session):
    tenant = Tenant(slug="t-058-candidate", name="T")
    session.add(tenant)
    session.flush()
    project = Project(tenant_id=tenant.id, slug="p", name="P")
    session.add(project)
    session.flush()
    job = Job(project_id=project.id, source_sha256="a" * 64, status="completed")
    session.add(job)
    session.flush()
    return tenant, project, job


def test_approve_candidate_creates_project_curated_concept(session):
    tenant, project, job = _job(session)
    candidate = enqueue_candidate(
        session,
        job=job,
        tenant_id=tenant.id,
        project_id=project.id,
        source_term="primary endpoint",
        observed_target="主要终点评估",
        suggested_target="主要终点",
        term_type="endpoint",
        risk="normal",
        confidence=0.91,
    )

    result = decide_candidate(
        session,
        candidate=candidate,
        actor_sub="reviewer",
        action="approve",
        expected_version=1,
        target_term="主要终点评估",
    )
    session.commit()

    concept = session.get(Concept, result["concept_id"])
    assert concept is not None
    assert concept.status == "curated"
    assert concept.layer == "project"
    assert concept.project_id == project.id
    assert [term.text for term in concept.terms] == ["primary endpoint", "主要终点评估"]
    assert result["candidate"]["status"] == "approved"
    assert result["candidate"]["version"] == 2


def test_reject_candidate_does_not_create_concept(session):
    tenant, project, job = _job(session)
    candidate = enqueue_candidate(
        session,
        job=job,
        tenant_id=tenant.id,
        project_id=project.id,
        source_term="ambiguous term",
        observed_target="不确定译法",
    )

    result = decide_candidate(
        session,
        candidate=candidate,
        actor_sub="reviewer",
        action="reject",
        expected_version=1,
        note="不是专业术语",
    )
    session.commit()

    assert result["concept_id"] is None
    assert session.scalars(select(Concept)).all() == []
    assert result["candidate"]["status"] == "rejected"


def test_candidate_version_conflict_is_rejected(session):
    tenant, project, job = _job(session)
    candidate = enqueue_candidate(
        session,
        job=job,
        tenant_id=tenant.id,
        project_id=project.id,
        source_term="study acronym",
        observed_target="研究缩写",
    )
    candidate.version = 2
    session.flush()

    with pytest.raises(CandidateConflict):
        decide_candidate(
            session,
            candidate=candidate,
            actor_sub="reviewer",
            action="approve",
            expected_version=1,
            target_term="研究缩写",
        )


def test_list_candidates_is_tenant_and_job_scoped(session):
    tenant, project, job = _job(session)
    enqueue_candidate(
        session,
        job=job,
        tenant_id=tenant.id,
        project_id=project.id,
        source_term="drug name",
        observed_target="药名",
    )
    session.commit()

    assert len(list_candidates(session, tenant_id=tenant.id, job_id=job.id)) == 1
    assert list_candidates(session, tenant_id="other-tenant", job_id=job.id) == []


def test_approve_candidate_persists_aliases_and_abbreviations(session):
    tenant, project, job = _job(session)
    candidate = enqueue_candidate(
        session,
        job=job,
        tenant_id=tenant.id,
        project_id=project.id,
        source_term="adverse event",
        observed_target="不良事件",
        term_type="safety",
    )

    result = decide_candidate(
        session,
        candidate=candidate,
        actor_sub="reviewer",
        action="approve",
        expected_version=1,
        target_term="不良事件",
        aliases=["adverse events", "AE"],
        abbreviations=["AE"],
    )
    session.commit()

    concept = session.get(Concept, result["concept_id"])
    assert concept is not None
    assert concept.version == 2
    assert {(term.lang, term.text, term.role) for term in concept.terms} == {
        ("en", "adverse event", "preferred"),
        ("zh", "不良事件", "preferred"),
        ("en", "adverse events", "synonym"),
        ("en", "AE", "abbreviation"),
    }
