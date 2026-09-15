# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy import select

from qyunslation.persist.candidate_repo import enqueue_candidate
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base, Job, Project, Tenant, TermDecision

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backfill_is_idempotent_and_does_not_change_status():
    reset_engine()
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    from qyunslation.persist.db import SessionLocal

    session = SessionLocal()
    try:
        tenant = Tenant(slug="t063f", name="T")
        session.add(tenant)
        session.flush()
        project = Project(tenant_id=tenant.id, slug="p", name="P")
        session.add(project)
        session.flush()
        job = Job(project_id=project.id, source_sha256="f" * 64, status="completed")
        session.add(job)
        session.flush()
        cand = enqueue_candidate(
            session, job=job, tenant_id=tenant.id, project_id=project.id, source_term="USA"
        )
        cand.status = "rejected"
        cand.decision_note = "plan062 purge: DENYLIST"
        cand.version = 2
        session.flush()
        backfill = _load("plan063e_backfill", ROOT / "scripts/plan063e-backfill-machine-decisions.py")
        first = backfill.backfill_machine_decisions(session)
        second = backfill.backfill_machine_decisions(session)
        session.flush()
        assert first == 1
        assert second == 0
        assert cand.status == "rejected"
        rows = list(session.scalars(select(TermDecision)).all())
        assert len(rows) == 1
        assert rows[0].actor_sub == "plan062-purge"
    finally:
        session.close()
        reset_engine()
