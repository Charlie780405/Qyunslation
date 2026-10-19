# SPDX-License-Identifier: MPL-2.0
"""PLAN-079 stage B: the read-only baseline reports gate reasons, encoding families and violation reconciliation."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from qyunslation.persist import db as persist_db
from qyunslation.persist.models import DocumentTermCandidate, Job, Project, QaItem

from _plan078d_seed import make_app, seed_run, tenant_id

_SPEC = importlib.util.spec_from_file_location(
    "plan079_baseline", Path(__file__).resolve().parents[2] / "scripts" / "qa" / "plan079_baseline.py"
)
baseline = importlib.util.module_from_spec(_SPEC)
sys.modules["plan079_baseline"] = baseline
_SPEC.loader.exec_module(baseline)


def test_codepoint_families():
    assert baseline.classify_codepoints("abc�") == ["fffd"]
    assert baseline.classify_codepoints("x\x07y") == ["c0"]
    assert baseline.classify_codepoints("x\x85y") == ["c1"]
    assert baseline.classify_codepoints("cafÃ©") == ["mojibake"]
    assert baseline.classify_codepoints("normal text") == ["none"]


def test_uppercase_portuguese_names_are_not_mojibake():
    assert baseline.classify_codepoints("CENTRO EM SÃO PAULO") == ["mojibake_upper_name"]
    assert baseline.classify_codepoints("JOÃO SILVA") == ["mojibake_upper_name"]
    # a real UTF-8 mis-decode keeps the euro-sign sequence, so it stays a mojibake hit
    assert baseline.classify_codepoints("itâ€™s") == ["mojibake"]


def test_violation_reconciliation():
    qa = {"c1": ["blocker"], "c2": ["warning"]}
    assert baseline.reconcile_violation("c1", qa) == "matched_blocker"
    assert baseline.reconcile_violation("c2", qa) == "matched_warning"
    assert baseline.reconcile_violation("c3", qa) == "unmatched"
    assert baseline.reconcile_violation(None, qa) == "no_concept_id"


def _candidate(session, run, tenant, project, job, source, status, risk="normal", concept=None, reason=""):
    session.add(DocumentTermCandidate(
        job_id=job.id, translation_run_id=run.id, tenant_id=tenant, project_id=project.id,
        source_sha256="0" * 64, source_term=source, source_norm=source.lower(), status=status,
        risk=risk, term_type="general", concept_id=concept, extraction_metadata={"reason": reason},
    ))


def test_report_counts_runs_blocked_only_by_terms(monkeypatch, tmp_path):
    client = make_app(monkeypatch, tmp_path)
    tenant = tenant_id(client)
    with persist_db.SessionLocal() as session:
        project = Project(tenant_id=tenant, slug="p", name="p")
        session.add(project)
        session.flush()
        job = Job(project_id=project.id, source_sha256="0" * 64)
        session.add(job)
        session.flush()
        only_terms = seed_run(session, tenant, quality="review_ready", qa_summary={"open_blocker": 0})
        mixed = seed_run(session, tenant, quality="qa_blocked", qa_summary={"open_blocker": 2})
        _candidate(session, only_terms, tenant, project, job, "sensitivity analysis", "pending", reason="structured")
        _candidate(session, mixed, tenant, project, job, "ABC", "pending_admin", risk="high")
        _candidate(session, mixed, tenant, project, job, "drug-x", "violation", concept="c-blocker")
        _candidate(session, mixed, tenant, project, job, "drug-y", "violation", concept="c-missing")
        session.add(QaItem(
            run_id=mixed.id, generation=1, category="terminology", severity="blocker",
            code="TERM_HIGH_RISK_CONFLICT", message="m", evidence_json={"concept_id": "c-blocker"}, is_current=True,
        ))
        session.add(QaItem(
            run_id=mixed.id, generation=1, category="integrity", severity="blocker", code="TEXT_ENCODING_ARTIFACT",
            message="m", is_current=True,
            location_json={"anchors": [{"side": "translated", "page": 2, "excerpt": "ab�cd"},
                                       {"side": "translated", "page": 3, "excerpt": "JOÃO SILVA"}]},
        ))
        session.commit()

        report = baseline.build_report(session)

    assert report["gated_runs"] == 2
    assert report["only_unresolved_terms"] == 1
    assert report["gate_reasons"]["unresolved_terms"] == 2
    assert report["gate_reasons"]["qa_blockers"] == 1
    assert report["text_encoding_artifact"]["excerpt_families"] == {"fffd": 1, "mojibake_upper_name": 1}
    assert report["violation_reconciliation"] == {"total": 2, "matched_blocker": 1, "unmatched": 1}
    # the report never carries document words
    assert "sensitivity" not in json.dumps(report)


def test_shadow_report_lists_runs_the_new_rule_would_release():
    spec = importlib.util.spec_from_file_location(
        "plan079_shadow_report", Path(__file__).resolve().parents[2] / "scripts" / "qa" / "plan079_shadow_report.py"
    )
    shadow = importlib.util.module_from_spec(spec)
    sys.modules["plan079_shadow_report"] = shadow
    spec.loader.exec_module(shadow)
    from types import SimpleNamespace

    def run(rid, legacy, new, **extra):
        return SimpleNamespace(id=rid, term_summary={"gate_shadow": {"legacy_term_reasons": legacy, "new_term_reasons": new, **extra}})

    report = shadow.summarize([
        run("aaaaaaaa-1", ["unresolved_terms"], []),
        run("bbbbbbbb-2", ["unresolved_terms"], ["qa_blockers"], review_required=1, violation_findings=1),
        run("cccccccc-3", [], ["qa_blockers"], review_required=2, review_overflow=1),
        SimpleNamespace(id="dddddddd-4", term_summary={}),
    ])
    assert report["runs_with_shadow_record"] == 3
    assert report["released_by_new_rule"] == 1 and report["inspect_released_runs"] == ["aaaaaaaa"]
    assert report["newly_blocked_by_new_rule"] == 1 and report["inspect_newly_blocked_runs"] == ["cccccccc"]
    assert (report["review_required_total"], report["violation_findings_total"], report["review_overflow_total"]) == (3, 1, 1)
