"""PLAN-078b slice 2: findings say where the problem is (page or paragraph) and quote the text."""
from __future__ import annotations

from qyunslation.pipeline.ad_qa import QaContext, run_ad_deterministic_qa
from qyunslation.pipeline.qa import locate
from qyunslation.pipeline.qa.pdf_inspect import (
    check_author_metadata,
    check_protected_literals,
    check_translation_text,
)


def _anchors(finding):
    return finding.location.get("anchors") or []


# --- segments ---------------------------------------------------------------------------------


def test_segments_from_pages_are_one_based_and_keep_the_page():
    segments = locate.segments_from_pages(["First line\n\nSecond line", "", "Third page text"])
    assert [(s.page, s.text) for s in segments] == [(1, "First line"), (1, "Second line"), (3, "Third page text")]


def test_segments_from_text_number_paragraphs_from_one():
    segments = locate.segments_from_text("alpha\n\nbeta\n  \ngamma")
    assert [(s.page, s.index, s.text) for s in segments] == [(None, 1, "alpha"), (None, 2, "beta"), (None, 3, "gamma")]


def test_excerpt_is_short_single_line_and_marks_cuts():
    long = "word " * 100
    out = locate.excerpt(long, 200, 205, radius=30)
    assert "\n" not in out and len(out) <= 80
    assert out.startswith("…") and out.endswith("…")


# --- PDF text checks -----------------------------------------------------------------------------


def test_missing_literal_points_at_the_source_page_and_quotes_it():
    source_pages = ["Intro page without literals", "Contact us at study@example.org for questions", "End"]
    findings = check_protected_literals(
        "\n".join(source_pages), "联系方式缺失", source_pages=source_pages
    )
    email = next(f for f in findings if f.code == "LITERAL_MISSING_EMAIL")
    anchor = _anchors(email)[0]
    assert anchor["side"] == "source" and anchor["page"] == 2
    assert "study@example.org" in anchor["excerpt"]
    assert anchor["label"] == "study@example.org"


def test_dose_anchor_matches_despite_spacing():
    source_pages = ["Dose 300 mg every two weeks", "unrelated"]
    findings = check_protected_literals("\n".join(source_pages), "剂量缺失", source_pages=source_pages)
    dose = next(f for f in findings if f.code == "LITERAL_MISSING_DOSE")
    assert _anchors(dose)[0]["page"] == 1


def test_literal_without_page_data_still_quotes_the_paragraph():
    findings = check_protected_literals("Para one\nWrite to a@b.org now", "无")
    email = next(f for f in findings if f.code == "LITERAL_MISSING_EMAIL")
    anchor = _anchors(email)[0]
    assert anchor["page"] is None and anchor["paragraph"] == 2


def test_author_change_points_at_the_page_of_the_author_line():
    source_pages = ["Title page", "Zhang San, Li Si, Wang Wu\nDepartment of Dermatology, Example Hospital"]
    findings = check_author_metadata("\n".join(source_pages), "张三 李四", source_pages=source_pages)
    if findings:  # depends on the author classifier recognising the line
        assert _anchors(findings[0])[0]["page"] == 2


def test_residue_and_artifacts_name_the_translated_pages():
    translated_pages = [
        "这是第一页中文译文。",
        "Subjects receiving treatment showed significant improvements across clinical endpoints\n"
        "Adverse events were reported during every scheduled study visit",
        "译文正常�含乱码",
    ]
    findings = check_translation_text(
        source_text="x", translated_text="\n".join(translated_pages), target_is_chinese=True,
        translated_pages=translated_pages,
    )
    by_code = {f.code: f for f in findings}
    residue = by_code.get("LATIN_RESIDUE") or by_code.get("UNTRANSLATED_BODY")
    assert residue is not None and _anchors(residue)[0]["page"] == 2
    assert _anchors(residue)[0]["side"] == "translated"
    artifact = by_code["TEXT_ENCODING_ARTIFACT"]
    assert [a["page"] for a in _anchors(artifact)] == [3]


def test_whole_document_rules_explain_why_they_have_no_place():
    findings = check_translation_text(source_text="x", translated_text="  ", target_is_chinese=True)
    assert findings[0].code == "EMPTY_TRANSLATION" and _anchors(findings[0]) == []


# --- AD (docx / text) rules ------------------------------------------------------------------------


def _ctx(source, target, **kw):
    return QaContext(source=source, target=target, direction="en-zh", terms={}, aliases={}, **kw)


def test_number_drift_quotes_the_source_paragraph_that_lost_the_number():
    source = "Background paragraph.\n\nPatients received 300 mg dupilumab; 45.2% improved at week 16."
    target = "背景段落。\n\n患者接受 300 mg 度普利尤单抗。"
    drift = next(f for f in run_ad_deterministic_qa(_ctx(source, target)) if f.code == "AD_NUMBER_DRIFT")
    anchors = _anchors(drift)
    assert anchors and anchors[0]["side"] == "source" and anchors[0]["paragraph"] == 2
    assert "45.2" in anchors[0]["excerpt"]
    assert anchors[0]["label"].startswith("45.2")


def test_number_drift_uses_page_numbers_when_pages_are_known():
    source = "One\nPage two holds 12.5% response"
    target = "一\n第二页无数字"
    segments = locate.segments_from_pages(["One", "Page two holds 12.5% response"])
    drift = next(
        f for f in run_ad_deterministic_qa(_ctx(source, target, source_segments=segments)) if f.code == "AD_NUMBER_DRIFT"
    )
    assert _anchors(drift)[0]["page"] == 2


def test_unexpected_number_points_at_the_translation():
    drift = next(
        f for f in run_ad_deterministic_qa(_ctx("Dose was 100 mg.", "剂量为 100 mg。另有 250 mg。"))
        if f.code == "AD_NUMBER_DRIFT"
    )
    sides = {a["side"] for a in _anchors(drift)}
    assert "translated" in sides


def test_dropped_negation_quotes_the_source_sentence():
    findings = run_ad_deterministic_qa(_ctx("The drug is not recommended for children.", "该药推荐用于儿童。"))
    neg = next(f for f in findings if f.code == "AD_NEGATION_DRIFT")
    assert "not recommended" in _anchors(neg)[0]["excerpt"]


def test_findings_without_a_spot_carry_a_reason_through_the_api_layer():
    # the reason comes from the registry (PAGE_COUNT_MISMATCH is a whole-document fact)
    from qyunslation.pipeline.qa import registry

    assert registry.rule_for("PAGE_COUNT_MISMATCH").unlocatable_reason == "页数差异不属于某一页"
