"""PLAN-083c：去掉没有实际意义的 QA 警告（网址零宽字符/换行碎片、低风险术语同义译法）。"""
from __future__ import annotations

from qyunslation.pipeline.qa.pdf_inspect import check_protected_literals
from qyunslation.pipeline.term_snapshot import (
    check_terms_in_translation,
    snapshot_hash,
)

Z = "\u200b"


def test_url_with_zero_width_spaces_and_line_breaks_is_not_reported():
    src = (
        f"see https://{Z}doi.{Z}org/{Z}10.{Z}1007/{Z}s13555-{Z}025-{Z}01368-4. and "
        f"https://{Z}\ndoi.{Z}org/{Z}10.{Z}1016/{Z}s0091-{Z}\n6749"
    )
    tr = "见 https://doi.org/10.1007/s13555-025-01368-4。 https://doi.org/10.1016/s0091-6749"
    assert check_protected_literals(src, tr) == []


def test_url_really_lost_is_still_reported():
    src = f"https://{Z}doi.{Z}org/{Z}10.{Z}1007/{Z}s13555-{Z}025-{Z}01368-4"
    found = check_protected_literals(src, "没有网址")
    assert [f.code for f in found] == ["LITERAL_MISSING_URL"]


def _snapshot(*terms):
    snap = {"status": "ready", "terms": list(terms)}
    snap["content_hash"] = snapshot_hash(snap)
    return snap


def _term(source, target, risk):
    return {
        "concept_id": f"c-{source}",
        "source_term": source,
        "preferred_target": target,
        "hard_constraint": True,
        "risk": risk,
        "source_hits": [{"start": 0, "end": len(source), "matched_text": source}],
    }


def test_low_risk_term_synonym_not_reported_but_high_risk_is(monkeypatch):
    monkeypatch.delenv("QYUNSLATION_QA_LOW_RISK_TERM_WARN", raising=False)
    snap = _snapshot(
        _term("discontinuation", "停药", "low"),
        _term("dupilumab", "度普利尤单抗", "high"),
    )
    codes = [f.code for f in check_terms_in_translation(snap, "因不良事件停止治疗，使用杜匹鲁单抗")]
    assert codes == ["TERM_HIGH_RISK_CONFLICT"]


def test_low_risk_term_warning_can_be_restored(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_QA_LOW_RISK_TERM_WARN", "on")
    snap = _snapshot(_term("discontinuation", "停药", "low"))
    codes = [f.code for f in check_terms_in_translation(snap, "停止治疗")]
    assert codes == ["TERM_TARGET_MISSING"]
