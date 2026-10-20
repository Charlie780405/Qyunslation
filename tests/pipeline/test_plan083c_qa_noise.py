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


# ---- 参考文献区：保持原文，不报网址缺失/英文残留 ----------------------------------------------------

def _check(source: str, translated: str):
    from qyunslation.pipeline.qa.pdf_inspect import check_translation_text

    return [f.code for f in check_translation_text(source_text=source, translated_text=translated)]


def test_urls_in_reference_section_are_not_reported():
    body = "Subjects received 300 mg Q2W."
    src = f"{body}\nReferences\n1. Smith J. Lancet 2024;1:2. https://doi.org/10.1016/xyz\nAppendix\nok"
    tr = "受试者接受 300 mg Q2W。\n附录\nok"
    assert "LITERAL_MISSING_URL" not in _check(src, tr)


def test_url_in_body_before_references_is_still_reported():
    src = "Details at https://example.org/protocol.\nReferences\n1. Smith J. https://doi.org/10.1/x"
    assert "LITERAL_MISSING_URL" in _check(src, "详见方案。")


def test_english_reference_lines_do_not_count_as_untranslated_residue():
    refs = "\n".join(
        f"{i}. Smith J, Jones K, Brown L, Green M, White N. Randomized trial of dupilumab in adults. Lancet 2024;1:{i}."
        for i in range(1, 9)
    )
    tr = "这是中文正文第一段。\n这是中文正文第二段。\nReferences\n" + refs
    assert "LATIN_RESIDUE" not in _check("src", tr) and "UNTRANSLATED_BODY" not in _check("src", tr)
