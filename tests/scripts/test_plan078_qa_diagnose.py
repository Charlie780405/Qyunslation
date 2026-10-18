"""PLAN-078a: the QA diagnosis script reports patterns, stays read-only and never prints content."""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from qyunslation.persist.models import Base, PreflightRecord, QaItem, Tenant, TranslationRunRecord

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "plan078-qa-diagnose.py"
NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
SECRET_NAME = "confidential-merger-protocol.pdf"


def _load():
    spec = importlib.util.spec_from_file_location("plan078_diagnose", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed(session):
    tenant = Tenant(slug="pilot", name="pilot")
    session.add(tenant)
    session.flush()

    def make(key, *, status, quality, fmt="pdf", domain="general", direction="English → 简体中文", days_ago=1, items=(), generation=1):
        pf = PreflightRecord(
            tenant_id=tenant.id, actor_sub="u", source_filename=SECRET_NAME, source_format=fmt,
            source_sha256=key.ljust(64, "0"), size_bytes=1, storage_key=key, expires_at=NOW + timedelta(days=1),
        )
        session.add(pf)
        session.flush()
        run = TranslationRunRecord(
            preflight_id=pf.id, tenant_id=tenant.id, actor_sub="u", idempotency_key_hash=key.ljust(64, "1"),
            direction=direction, profile="p", status=status, quality_state=quality, generation=generation,
            model_profile_id="internal-qwen-quality", document_classification="internal",
            settings_snapshot={"domain_profile": domain},
            created_at=NOW - timedelta(days=days_ago), updated_at=NOW - timedelta(days=days_ago),
            completed_at=NOW - timedelta(days=days_ago) + timedelta(hours=2) if quality == "approved" else None,
        )
        session.add(run)
        session.flush()
        for severity, code, located, rule in items:
            session.add(
                QaItem(
                    run_id=run.id, generation=generation, category="x", severity=severity, code=code, message="m",
                    object_id="obj-1" if located else None,
                    evidence_json={"rule_version": rule} if rule else {"text": "SECRET BODY TEXT"},
                )
            )
        return run

    make("a", status="gated", quality="qa_blocked", fmt="docx", domain="ad",
         items=[("blocker", "AD_NUMBER_DRIFT", False, "076-qa-v1")])
    make("b", status="gated", quality="qa_blocked", fmt="docx", domain="ad",
         items=[("blocker", "AD_NUMBER_DRIFT", False, None)])
    make("c", status="gated", quality="qa_unavailable", items=[("unavailable", "TERM_EXTRACTION_DEGRADED", False, "076-qa-v1")])
    make("d", status="succeeded", quality="approved")
    make("e", status="interrupted", quality="qa_blocked", items=[("blocker", "LOGO_MISSING", True, "076-qa-v1")])
    make("f", status="translating", quality="review_ready")  # finished executor still labelled translating
    make("g", status="succeeded", quality="approved", days_ago=200)  # outside the window
    old_generation = make("h", status="gated", quality="review_ready", generation=2,
                          items=[("blocker", "OLD_GEN_CODE", False, None)])
    # An item from a superseded generation must not be counted.
    session.add(QaItem(run_id=old_generation.id, generation=1, category="x", severity="blocker",
                       code="STALE_GENERATION", message="m", evidence_json={}))
    session.commit()


@pytest.fixture()
def session():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        _seed(s)
        yield s


def test_report_groups_blockers_by_code_and_dimension(session):
    report = _load().collect(session, days=30, now=NOW)
    assert report["runs"] == 7  # the 200-day-old run is outside the window
    codes = {row["code"]: row for row in report["codes"]}
    drift = codes["AD_NUMBER_DRIFT"]
    assert drift["runs"] == 2 and drift["items"] == 2
    assert drift["format"] == {"docx": 2} and drift["domain"] == {"ad": 2}
    assert drift["rule_version"] == {"076-qa-v1": 1, "(none)": 1}
    assert drift["located_share"] == 0.0
    assert codes["LOGO_MISSING"]["located_share"] == 1.0
    assert codes["TERM_EXTRACTION_DEGRADED"]["severity"] == "unavailable"
    assert "STALE_GENERATION" not in codes  # only the run's current generation counts


def test_rates_separate_quality_blocks_from_service_trouble(session):
    report = _load().collect(session, days=30, now=NOW)
    assert report["reached_qa"] == 7
    assert report["qa_blocked"] == 3 and report["qa_unavailable"] == 1
    assert report["qa_blocked_rate"] == round(3 / 7, 3)
    assert report["median_hours_created_to_approved"] == 2.0


def test_inconsistent_state_is_reported_not_changed(session):
    report = _load().collect(session, days=30, now=NOW)
    assert report["inconsistent"]["interrupted_while_at_gate"] == 1
    assert report["inconsistent"]["translating_while_at_gate"] == 1
    assert session.scalar(sa.select(sa.func.count()).select_from(TranslationRunRecord)) == 8


def test_output_never_contains_file_names_or_evidence_text(session):
    module = _load()
    report = module.collect(session, days=30, now=NOW)
    for rendered in (module.render_text(report), json.dumps(report, ensure_ascii=False)):
        assert SECRET_NAME not in rendered
        assert "SECRET BODY TEXT" not in rendered


def test_cli_runs_against_a_database_file_and_is_read_only(tmp_path, capsys):
    url = f"sqlite+pysqlite:///{tmp_path / 'diag.sqlite'}"
    engine = sa.create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        _seed(s)
    engine.dispose()
    module = _load()
    assert module.main(["--database-url", url, "--days", "3650", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["runs"] == 8
    with sa.create_engine(url).connect() as conn:
        assert conn.scalar(sa.text("SELECT count(*) FROM translation_run_record")) == 8
    from qyunslation.persist.db import reset_engine

    reset_engine()
