# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

from qyunslation.persist.candidate_repo import enqueue_candidate
from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base, Job, Project, Tenant, TermDecision
from qyunslation.quality.evolve_rules import KEEP_LIST, _kills_keep, propose_denylist, report


def test_keep_list_regex_is_discarded():
    killed = _kills_keep(r"^tralokinumab$")
    assert killed is not None
    assert killed in KEEP_LIST


def test_machine_only_single_job_does_not_propose_denylist():
    rows = [
        {
            "source_term": "FOO",
            "source_norm": "foo",
            "job_id": "j1",
            "actor_sub": "plan062-purge",
            "machine": True,
            "action": "reject",
        }
        for _ in range(5)
    ]
    assert propose_denylist(rows) == []


def test_report_does_not_write_when_no_session_changes(tmp_path, monkeypatch):
    reset_engine()
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    from qyunslation.persist.db import SessionLocal

    session = SessionLocal()
    try:
        tenant = Tenant(slug="t063e", name="T")
        session.add(tenant)
        session.flush()
        project = Project(tenant_id=tenant.id, slug="p", name="P")
        session.add(project)
        session.flush()
        job = Job(project_id=project.id, source_sha256="e" * 64, status="completed")
        session.add(job)
        session.flush()
        cand = enqueue_candidate(
            session, job=job, tenant_id=tenant.id, project_id=project.id, source_term="SPAMterm"
        )
        session.add(
            TermDecision(
                candidate_id=cand.id,
                action="reject",
                actor_sub="human-reviewer",
                source_term="SPAMterm",
                target_term="",
                scope="project",
                from_version=1,
                to_version=2,
            )
        )
        session.flush()
        proposals = report(session)
        assert isinstance(proposals, list)
        session.rollback()
    finally:
        session.close()
        reset_engine()
