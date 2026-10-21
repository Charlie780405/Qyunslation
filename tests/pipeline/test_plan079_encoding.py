# SPDX-License-Identifier: MPL-2.0
"""PLAN-079 stage D: garbled-text findings carry code points and do not blame the translation for the source's own characters."""
from __future__ import annotations

import pytest

from qyunslation.pipeline.qa.pdf_inspect import check_translation_text
from qyunslation.structure.text_sanitize import artifact_evidence, detect_text_artifacts


def _by_code(findings):
    return {f.code: f for f in findings}


@pytest.mark.parametrize("text", ["JOÃO SILVA", "CENTRO EM SÃO PAULO", "Hospital São Paulo", "患者比例<5%"])
def test_real_names_and_clean_text_are_not_garbled(text):
    assert detect_text_artifacts(text) == []


@pytest.mark.parametrize("text", ["itâ€™s", "cafÃ©", "Ã\xa0 la", "x�y", "a\x07b", "a\x85b"])
def test_real_garbling_is_still_detected(text):
    assert "TEXT_ENCODING_ARTIFACT" in detect_text_artifacts(text)


def test_evidence_names_the_detector_and_code_point():
    assert artifact_evidence("a\x07b�") == {"fffd": ["U+FFFD"], "c0": ["U+0007"]}
    assert artifact_evidence("cafÃ©") == {"mojibake": ["U+00C3"]}
    assert artifact_evidence("clean") == {}


def test_blocker_lists_every_garbled_page_with_detectors():
    pages = [f"第{n}页正常" for n in range(1, 8)]
    for n in (2, 3, 4, 5, 6, 7):
        pages[n - 1] += "\x07"
    found = _by_code(check_translation_text(source_text="x", translated_text="\n".join(pages), translated_pages=pages))
    item = found["TEXT_ENCODING_ARTIFACT"]
    assert item.severity == "blocker"
    assert item.evidence["pages"] == [2, 3, 4, 5, 6, 7]
    assert item.evidence["detectors"] == {"c0": ["U+0007"]}
    assert [a["page"] for a in item.location["anchors"]] == [2, 3, 4, 5, 6, 7]
    assert "TEXT_ENCODING_INHERITED" not in found


def test_characters_already_on_the_same_source_page_are_not_blamed_on_the_translation(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_ENCODING_INHERITANCE", "1")
    source = ["正常", "原文\x07带控制字符", "正常"]
    translated = ["正常译文", "译文\x07带控制字符", "正常译文�"]
    found = _by_code(check_translation_text(
        source_text="\n".join(source), translated_text="\n".join(translated),
        source_pages=source, translated_pages=translated,
    ))
    inherited, blocker = found["TEXT_ENCODING_INHERITED"], found["TEXT_ENCODING_ARTIFACT"]
    assert inherited.severity == "info" and inherited.evidence["pages"] == [2]
    assert blocker.severity == "blocker" and blocker.evidence["pages"] == [3]
    assert blocker.evidence["detectors"] == {"fffd": ["U+FFFD"]}


def test_all_pages_inherited_leaves_no_blocker(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_ENCODING_INHERITANCE", "1")
    source = ["原文\x07"]
    translated = ["译文\x07"]
    found = _by_code(check_translation_text(
        source_text=source[0], translated_text=translated[0], source_pages=source, translated_pages=translated,
    ))
    assert "TEXT_ENCODING_ARTIFACT" not in found and "TEXT_ENCODING_INHERITED" in found


def test_page_counts_that_differ_never_count_as_inherited(monkeypatch):
    monkeypatch.setenv("QYUNSLATION_ENCODING_INHERITANCE", "1")
    source = ["原文\x07", "第二页"]
    translated = ["译文\x07"]
    found = _by_code(check_translation_text(
        source_text="\n".join(source), translated_text=translated[0], source_pages=source, translated_pages=translated,
    ))
    assert found["TEXT_ENCODING_ARTIFACT"].evidence["source_compared"] is False
    assert "TEXT_ENCODING_INHERITED" not in found


def test_without_page_text_the_finding_still_carries_detectors():
    found = _by_code(check_translation_text(source_text="x", translated_text="坏�字"))
    assert found["TEXT_ENCODING_ARTIFACT"].evidence["detectors"] == {"fffd": ["U+FFFD"]}


def test_default_auto_downgrades_only_inherited_unmapped_marks(monkeypatch):
    """Default is auto: source-inherited C0/U+FFFD marks warn; extra marks or mojibake still block."""
    monkeypatch.delenv("QYUNSLATION_ENCODING_INHERITANCE", raising=False)
    source = ["原文\x07带控制字符"]
    same = ["译文\x07带控制字符"]
    found = _by_code(check_translation_text(
        source_text=source[0], translated_text=same[0], source_pages=source, translated_pages=same,
    ))
    assert "TEXT_ENCODING_ARTIFACT" not in found and "TEXT_ENCODING_INHERITED" in found
    more = ["译文\x07\x07\x07带控制字符"]
    found = _by_code(check_translation_text(
        source_text=source[0], translated_text=more[0], source_pages=source, translated_pages=more,
    ))
    assert found["TEXT_ENCODING_ARTIFACT"].severity == "blocker"
    clean = ["原文干净"]
    found = _by_code(check_translation_text(
        source_text=clean[0], translated_text=same[0], source_pages=clean, translated_pages=same,
    ))
    assert found["TEXT_ENCODING_ARTIFACT"].severity == "blocker"


def test_bilingual_pdf_allows_two_copies_of_inherited_marks(monkeypatch):
    monkeypatch.delenv("QYUNSLATION_ENCODING_INHERITANCE", raising=False)
    source = ["原文\x07"]
    dual = ["原文\x07译文\x07"]
    found = _by_code(check_translation_text(
        source_text=source[0], translated_text=dual[0], source_pages=source, translated_pages=dual, bilingual=True,
    ))
    assert "TEXT_ENCODING_ARTIFACT" not in found
    found = _by_code(check_translation_text(
        source_text=source[0], translated_text=dual[0], source_pages=source, translated_pages=dual,
    ))
    assert found["TEXT_ENCODING_ARTIFACT"].severity == "blocker"


def test_babeldoc_space_glyph_control_is_warning_not_blocker():
    """PLAN-082 S4: U+0003 between name parts is a ToUnicode space-map artifact, not real mojibake."""
    pages = [
        "Yue\x03Cheng\x03 1†，Qingfeng\x03Liu 2†",
        "MAD\x03阶段共纳入\x0324\x03名参与者",
        "3.00\x03ng/mL。",
    ]
    found = _by_code(check_translation_text(
        source_text="clean source", translated_text="\n".join(pages), translated_pages=pages,
    ))
    assert "TEXT_ENCODING_ARTIFACT" not in found
    item = found["TEXT_LAYER_SPACE_MAP"]
    assert item.severity == "warning"
    assert item.evidence["pages"] == [1, 2, 3]
    assert "U+0003" in item.evidence["detectors"]["c0"]
    snippet = item.location["anchors"][0]["excerpt"]
    assert "⟦U+0003⟧" in snippet
    assert "\x03" not in snippet


def test_real_replacement_char_still_blocks_even_beside_space_map():
    pages = ["Yue\x03Cheng 正常", "坏\ufffd字"]
    found = _by_code(check_translation_text(
        source_text="x", translated_text="\n".join(pages), translated_pages=pages,
    ))
    assert found["TEXT_ENCODING_ARTIFACT"].severity == "blocker"
    assert found["TEXT_ENCODING_ARTIFACT"].evidence["pages"] == [2]
    assert found["TEXT_LAYER_SPACE_MAP"].evidence["pages"] == [1]


def test_garbled_text_can_be_waived_by_one_reviewer_but_other_critical_facts_cannot():
    from qyunslation.pipeline.qa import registry

    rules = {rule.code: rule for rule in registry.all_rules()}
    assert rules["TEXT_ENCODING_ARTIFACT"].rule_class == "C2"
    assert "grant_waiver" in registry.allowed_actions("C2", "reviewer", is_writer=False)
    # numbers, negation and the like stay C1: no waiver, a second person must confirm a false positive
    assert rules["AD_NUMBER_DRIFT"].rule_class == "C1"
    assert "grant_waiver" not in registry.allowed_actions("C1", "reviewer", is_writer=False)
