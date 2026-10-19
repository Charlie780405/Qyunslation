# SPDX-License-Identifier: MPL-2.0
"""PLAN-079 stage C: vocabulary candidates stop gating delivery; real document term risks still do."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from _plan078d_seed import make_app, seed_run, tenant_id

from qyunslation.api.v1 import _formal_gate, _term_review_findings
from qyunslation.persist import db as persist_db
from qyunslation.persist.models import DocumentTermCandidate, DocumentTermOccurrence, Job, PreflightRecord, Project
from qyunslation.pipeline.qa import registry
from qyunslation.pipeline.qa.engine import QaFinding
from qyunslation.pipeline.qa.term_review import (
    MAX_PER_DOCUMENT,
    distinct_targets,
    is_review_type,
    review_required_findings,
    term_gate_mode,
    violation_findings,
)


def cand(source, target="", *, term_type="drug", status="pending", match="candidate", concept=None, pages=(), suggested=None):
    return SimpleNamespace(
        source_term=source, source_norm=source.lower(), observed_target=target, term_type=term_type,
        status=status, match_type=match, concept_id=concept, suggested_target=suggested,
        occurrences=[SimpleNamespace(page_no=p, source_context=f"ctx {source}") for p in pages],
    )


def test_mode_defaults_to_legacy_and_ignores_garbage():
    assert term_gate_mode("") == "legacy"
    assert term_gate_mode("bogus") == "legacy"
    assert [term_gate_mode(m) for m in ("Shadow", " enforce ", "legacy")] == ["shadow", "enforce", "legacy"]


def test_review_types_cover_english_and_chinese_labels():
    for t in ("drug", "target", "safety_event", "endpoint", "药物", "安全性事件", "量表/终点/方法", "基因/蛋白/受体/细胞因子/通路", "疾病"):
        assert is_review_type(t), t
    for t in ("general", "专业缩写", "code", "生物标志物", "监管机构或学会"):
        assert not is_review_type(t), t


def test_one_rendering_with_a_gloss_is_not_two_translations():
    assert distinct_targets(["自闭症", "自闭症（ASD）"]) == ["自闭症"]
    assert len(distinct_targets(["白细胞介素-4", "IL-4"])) == 2


def test_two_renderings_of_a_drug_need_review_with_page_evidence():
    rows = [cand("dupilumab", "度普利尤单抗", pages=(2,)), cand("dupilumab", "杜匹鲁单抗", pages=(5,))]
    findings, overflow = review_required_findings(rows)
    assert overflow == 0 and len(findings) == 1
    item = findings[0]
    assert item.code == "TERM_REVIEW_REQUIRED" and item.severity == "blocker"
    assert item.evidence["signal"] == "multi_target" and set(item.evidence["targets"]) == {"度普利尤单抗", "杜匹鲁单抗"}
    assert [a["page"] for a in item.location["anchors"]] == [2, 5]


@pytest.mark.parametrize(
    "rows",
    [
        [cand("dupilumab", "度普利尤单抗")],  # a single rendering
        [cand("sensitivity analysis", "敏感性分析", term_type="general"), cand("sensitivity analysis", "灵敏度分析", term_type="general")],  # not a review type
        [cand("x", "甲", term_type="general"), cand("x", "乙", term_type="general")],
        [cand("dupilumab", "甲", match="termbase"), cand("dupilumab", "乙", match="termbase")],  # resolved by the lexicon
        [cand("dupilumab", "甲", status="approved"), cand("dupilumab", "乙", status="rejected")],  # already decided
    ],
)
def test_no_review_without_a_real_conflict(rows):
    assert review_required_findings(rows) == ([], 0)


def test_lexicon_alias_conflict_is_a_review():
    terms = [
        {"source_term": "AD", "preferred_target": "特应性皮炎", "concept_id": "c1", "source_hits": [1]},
        {"source_term": "ad", "preferred_target": "阿尔茨海默病", "concept_id": "c2", "source_hits": [1]},
        {"source_term": "IL-4", "preferred_target": "白细胞介素-4", "concept_id": "c3", "source_hits": [1]},
        {"source_term": "unused", "preferred_target": "甲", "concept_id": "c4", "source_hits": []},
        {"source_term": "unused", "preferred_target": "乙", "concept_id": "c5", "source_hits": []},
    ]
    findings, _ = review_required_findings([], terms)
    assert [f.evidence["signal"] for f in findings] == ["alias_conflict"]
    assert findings[0].evidence["source_norm"] == "ad"


def test_review_count_is_capped_per_document():
    rows = []
    for n in range(MAX_PER_DOCUMENT + 3):
        rows += [cand(f"drug{n}", f"甲{n}"), cand(f"drug{n}", f"乙乙{n}")]
    findings, overflow = review_required_findings(rows)
    assert len(findings) == MAX_PER_DOCUMENT and overflow == 3


def test_violation_becomes_a_blocking_target_missing_unless_already_blocked():
    rows = [
        cand("drugA", status="violation", concept="c1", suggested="甲药", pages=(3,)),
        cand("drugA", status="violation", concept="c1", suggested="甲药", pages=(4,)),
        cand("drugB", status="violation", concept="c2", suggested="乙药", pages=(1,)),
        cand("drugC", status="pending"),
    ]
    findings = violation_findings(rows, covered_blockers=["c2"])
    assert [(f.code, f.severity, f.evidence["concept_id"]) for f in findings] == [("TERM_TARGET_MISSING", "blocker", "c1")]
    assert findings[0].evidence["source_hits"] == 2 and [a["page"] for a in findings[0].location["anchors"]] == [3, 4]


def test_registry_knows_the_new_code_as_a_blocking_term_rule():
    info = {rule.code: rule for rule in registry.all_rules()}["TERM_REVIEW_REQUIRED"]
    assert info.rule_class == "C4" and info.batchable is False
    assert info.identity_keys == ("source_norm", "signal")


# ---- the gate and the QA round, on a real database ----------------------------------------------------


def _seed(session, tenant, *, quality="review_ready", open_blocker=0):
    project = Project(tenant_id=tenant, slug="p", name="p")
    session.add(project)
    session.flush()
    job = Job(project_id=project.id, source_sha256="0" * 64)
    session.add(job)
    session.flush()
    run = seed_run(session, tenant, quality=quality, qa_summary={"open_blocker": open_blocker})
    return run, project, job


def _row(session, run, tenant, project, job, source, target, *, status="pending", term_type="drug", concept=None, suggested=None, page=None):
    row = DocumentTermCandidate(
        job_id=job.id, translation_run_id=run.id, tenant_id=tenant, project_id=project.id, source_sha256="0" * 64,
        source_term=source, source_norm=source.lower(), observed_target=target, term_type=term_type, status=status,
        concept_id=concept, suggested_target=suggested, extraction_metadata={},
    )
    session.add(row)
    session.flush()
    if page:
        session.add(DocumentTermOccurrence(candidate_id=row.id, page_no=page, source_context="ctx"))
    return row


def test_gate_modes_decide_whether_candidates_block(monkeypatch, tmp_path):
    client = make_app(monkeypatch, tmp_path)
    tenant = tenant_id(client)
    with persist_db.SessionLocal() as session:
        run, project, job = _seed(session, tenant)
        _row(session, run, tenant, project, job, "sensitivity analysis", "", term_type="general")
        session.commit()

        monkeypatch.delenv("QYUNSLATION_TERM_GATE_MODE", raising=False)
        legacy = _formal_gate(session, run)
        assert legacy["reasons"] == ["unresolved_terms"] and legacy["term_gate_mode"] == "legacy"

        monkeypatch.setenv("QYUNSLATION_TERM_GATE_MODE", "shadow")
        assert _formal_gate(session, run)["reasons"] == ["unresolved_terms"]

        monkeypatch.setenv("QYUNSLATION_TERM_GATE_MODE", "enforce")
        enforce = _formal_gate(session, run)
        assert enforce["passed"] is True and enforce["reasons"] == []
        # still reported for display
        assert enforce["unresolved_term_count"] == 1 and enforce["term_gate_mode"] == "enforce"


def test_qa_round_hook_is_inert_in_legacy_records_in_shadow_and_blocks_in_enforce(monkeypatch, tmp_path):
    client = make_app(monkeypatch, tmp_path)
    tenant = tenant_id(client)
    with persist_db.SessionLocal() as session:
        run, project, job = _seed(session, tenant)
        _row(session, run, tenant, project, job, "dupilumab", "度普利尤单抗", page=2)
        _row(session, run, tenant, project, job, "dupilumab", "杜匹鲁单抗", page=5)
        _row(session, run, tenant, project, job, "drugV", "", status="violation", concept="cv", suggested="乙药", page=7)
        session.commit()

        monkeypatch.delenv("QYUNSLATION_TERM_GATE_MODE", raising=False)
        assert _term_review_findings(session, run, []) == []
        assert "gate_shadow" not in (run.term_summary or {})

        monkeypatch.setenv("QYUNSLATION_TERM_GATE_MODE", "shadow")
        assert _term_review_findings(session, run, []) == []  # shadow never adds blockers
        shadow = run.term_summary["gate_shadow"]
        assert shadow["legacy_term_reasons"] == ["unresolved_terms"]
        assert shadow["new_term_reasons"] == ["qa_blockers"]
        assert shadow["review_required"] == 1 and shadow["violation_findings"] == 1

        monkeypatch.setenv("QYUNSLATION_TERM_GATE_MODE", "enforce")
        findings = _term_review_findings(session, run, [])
        assert sorted(f.code for f in findings) == ["TERM_REVIEW_REQUIRED", "TERM_TARGET_MISSING"]
        # a term the document-level check already blocks on is not reported twice
        covered = [QaFinding(category="terminology", severity="blocker", code="TERM_HIGH_RISK_CONFLICT",
                             message="m", evidence={"concept_id": "cv"})]
        again = _term_review_findings(session, run, covered)
        assert sorted(f.code for f in again) == ["TERM_REVIEW_REQUIRED"]


def test_degraded_term_extraction_produces_no_verdict(monkeypatch, tmp_path):
    client = make_app(monkeypatch, tmp_path)
    tenant = tenant_id(client)
    monkeypatch.setenv("QYUNSLATION_TERM_GATE_MODE", "enforce")
    with persist_db.SessionLocal() as session:
        run, project, job = _seed(session, tenant)
        run.term_summary = {"extraction_status": "degraded"}
        _row(session, run, tenant, project, job, "dupilumab", "甲")
        _row(session, run, tenant, project, job, "dupilumab", "乙乙")
        session.commit()
        assert _term_review_findings(session, run, []) == []


def test_each_generation_has_its_own_candidates(monkeypatch, tmp_path):
    """PLAN-078 Q10 closed: candidates belong to one generation's run, so a newer run starts clean."""
    client = make_app(monkeypatch, tmp_path)
    tenant = tenant_id(client)
    with persist_db.SessionLocal() as session:
        first, project, job = _seed(session, tenant)
        _row(session, first, tenant, project, job, "dupilumab", "甲")
        second = seed_run(session, tenant, generation=2, preflight=session.get(PreflightRecord, first.preflight_id))
        session.commit()
        monkeypatch.delenv("QYUNSLATION_TERM_GATE_MODE", raising=False)
        assert _formal_gate(session, first)["unresolved_term_count"] == 1
        assert _formal_gate(session, second)["unresolved_term_count"] == 0
