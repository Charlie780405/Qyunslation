# SPDX-License-Identifier: MPL-2.0
"""PLAN-062a：历史 pending 按规则与已入库 Concept 回扫。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from sqlalchemy import select

from qyunslation.persist.candidate_repo import enqueue_candidate
from qyunslation.persist.concept_repo import upsert_curated_from_entry
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base, Job, Project, Tenant, TermDecision
from qyunslation.glossary.governance import GlossaryEntry

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "plan062_purge", ROOT / "scripts" / "plan062-purge-stale-candidates.py"
)
assert _SPEC and _SPEC.loader
purge_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(purge_mod)


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
    tenant = Tenant(slug="t-062-purge", name="T")
    session.add(tenant)
    session.flush()
    project = Project(tenant_id=tenant.id, slug="p", name="P")
    session.add(project)
    session.flush()
    job = Job(project_id=project.id, source_sha256="b" * 64, status="completed")
    session.add(job)
    session.flush()
    return tenant, project, job


def test_purge_rejects_noise_applies_curated_and_keeps_unknown(session):
    tenant, project, job = _job(session)
    upsert_curated_from_entry(
        session,
        GlossaryEntry(
            source="EASI",
            target="EASI",
            src_lng="en",
            tgt_lng="en",
            layer="clinical",
            status="curated",
        ),
    )
    noise = enqueue_candidate(
        session,
        job=job,
        tenant_id=tenant.id,
        project_id=project.id,
        source_term="UK",
    )
    known = enqueue_candidate(
        session,
        job=job,
        tenant_id=tenant.id,
        project_id=project.id,
        source_term="EASI",
    )
    unknown = enqueue_candidate(
        session,
        job=job,
        tenant_id=tenant.id,
        project_id=project.id,
        source_term="tralokinumab",
    )
    dry = purge_mod.purge_stale_candidates(session, dry_run=True)
    assert dry == {"reject": 1, "apply": 1, "keep": 1}
    assert noise.status == "pending"
    applied = purge_mod.purge_stale_candidates(session, dry_run=False)
    session.flush()
    assert applied == {"reject": 1, "apply": 1, "keep": 1}
    assert noise.status == "rejected"
    assert known.status == "applied"
    assert known.concept_id
    assert unknown.status == "pending"
    decisions = list(session.scalars(select(TermDecision)).all())
    actions = {row.action for row in decisions}
    actors = {row.actor_sub for row in decisions}
    assert "reject" in actions
    assert "apply" in actions
    assert actors == {"plan062-purge"}
