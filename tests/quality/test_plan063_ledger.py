# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

from qyunslation.persist.db import init_engine, reset_engine
from qyunslation.persist.models import Base, Job, Project, Tenant, WorkbenchTranslationRun
from qyunslation.persist.candidate_repo import enqueue_candidate
from qyunslation.quality.ledger import record_run, screen_blindness, acceptance_rate


def _session(tmp_path, monkeypatch):
    reset_engine()
    monkeypatch.setenv("QYUNSLATION_QUALITY_LEDGER", str(tmp_path / "ledger.jsonl"))
    engine = init_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    from qyunslation.persist.db import SessionLocal

    assert SessionLocal is not None
    return SessionLocal()


def test_screen_blind_when_error_or_generic_ratio(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    try:
        tenant = Tenant(slug="t063", name="T")
        session.add(tenant)
        session.flush()
        project = Project(tenant_id=tenant.id, slug="p", name="P")
        session.add(project)
        session.flush()
        job = Job(project_id=project.id, source_sha256="c" * 64, status="review_ready")
        session.add(job)
        session.flush()
        run = WorkbenchTranslationRun(
            job_id=job.id,
            tenant_id=tenant.id,
            actor_sub="tester",
            source_format="pdf",
            status="review_ready",
        )
        session.add(run)
        session.flush()
        blind = screen_blindness(
            {
                "SCREEN_GENERIC": 8,
                "extracted_total": 10,
                "screen_origin": {"error": 1, "llm": 2},
            }
        )
        assert blind["screen_blind"] is True
        record = record_run(
            session,
            run=run,
            excluded_stats={
                "SCREEN_GENERIC": 8,
                "extracted_total": 10,
                "screen_origin": {"error": 1},
            },
            candidate_summary={"pending": 0, "applied": 1},
        )
        assert record["screen_blind"] is True
        assert (tmp_path / "ledger.jsonl").is_file()
    finally:
        session.close()
        reset_engine()


def test_acceptance_rate_dedupes_source_norm(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch)
    try:
        tenant = Tenant(slug="t063b", name="T")
        session.add(tenant)
        session.flush()
        project = Project(tenant_id=tenant.id, slug="p", name="P")
        session.add(project)
        session.flush()
        job = Job(project_id=project.id, source_sha256="d" * 64, status="completed")
        session.add(job)
        session.flush()
        first = enqueue_candidate(
            session, job=job, tenant_id=tenant.id, project_id=project.id, source_term="dermatitis"
        )
        second = enqueue_candidate(
            session,
            job=job,
            tenant_id=tenant.id,
            project_id=project.id,
            source_term="Dermatitis",
            observed_target="皮炎",
        )
        first.status = "approved"
        second.status = "approved"
        session.flush()
        assert acceptance_rate(session, tenant_id=tenant.id) == 1.0
    finally:
        session.close()
        reset_engine()
