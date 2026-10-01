# SPDX-License-Identifier: MPL-2.0
"""PLAN-045c：IL 标记消毒与叠印检测。"""
from __future__ import annotations

from qyunslation.structure.text_sanitize import (
    IL_MARKUP_LEAK,
    SOURCE_OVERLAY,
    TEXT_ENCODING_ARTIFACT,
    detect_source_overlay,
    detect_text_artifacts,
    has_il_markup_leak,
    sanitize_translated_text,
    strip_il_markup,
)


def test_strip_span_markup():
    dirty = (
        "纳入<span style='id:3'>患者</span>"
        "<span style='id:5'> </span>=337"
        "<span st yle='id:12'>。</span>"
    )
    cleaned = strip_il_markup(dirty)
    assert "<span" not in cleaned.lower()
    assert "style=" not in cleaned.lower()
    assert "患者" in cleaned
    assert "=337" in cleaned


def test_sanitize_idempotent_clean_text():
    text = "曲罗芦单抗每4周给药一次的免疫原性评估"
    out, codes = sanitize_translated_text(text)
    assert out == text
    assert codes == []


def test_sanitize_forces_endpoint_calque():
    out, codes = sanitize_translated_text("患者达到皮肤清晰或几乎清晰")
    assert "皮损完全清除或几乎清除" in out
    assert "皮肤清晰" not in out
    assert codes == []


def test_sanitize_forces_leftover_english_phrase():
    out, _codes = sanitize_translated_text(
        "Patients achieved clear or almost clear skin."
    )
    assert "皮损完全清除或几乎清除" in out
    assert "皮肤清晰" not in out


def test_sanitize_does_not_expand_q2w_abbreviation():
    text = "每2周一次（Q2W）与每4周一次（Q4W）维持给药"
    out, codes = sanitize_translated_text(text)
    assert out == text
    assert codes == []


def test_sanitize_collapses_nested_q2w():
    out, _codes = sanitize_translated_text(
        "包括每2周一次（每 2 周一次（Q2W））和每4周一次（每 4 周一次（Q4W））"
    )
    assert "每2周一次（每" not in out
    assert "每2周一次（Q2W）" in out
    assert "每4周一次（Q4W）" in out


def test_sanitize_marks_uncleared_leak():
    # 畸形残留无法完全剥掉时记 IL_MARKUP_LEAK
    leftover = "患者<span"
    cleaned, codes = sanitize_translated_text(leftover)
    assert has_il_markup_leak(cleaned) or IL_MARKUP_LEAK in codes


def test_sanitize_removes_misspelled_style_tags_and_control_characters():
    dirty = "因<stytle\x03id='3'>1年严重日光敏感病史</stytle>就诊。"
    cleaned, codes = sanitize_translated_text(dirty)
    assert cleaned == "因1年严重日光敏感病史就诊。"
    assert "stytle" not in cleaned.casefold()
    assert "\x03" not in cleaned
    assert codes == []


def test_text_artifact_detection_blocks_replacement_and_mojibake_but_not_comparison():
    assert detect_text_artifacts("患者比例<5%，IL-13 和 IFN-γ保持不变") == []
    assert TEXT_ENCODING_ARTIFACT in detect_text_artifacts("错误字符�")
    assert TEXT_ENCODING_ARTIFACT in detect_text_artifacts("itâ€™s corrupted")
    assert IL_MARKUP_LEAK in detect_text_artifacts("<stytle id='5'>残留")


def test_overlay_detection_warns_on_mixed_residue():
    page = (
        "背景 曲罗芦单抗是一种抗白细胞介素-13单抗。" * 3
        + " Predicting successful dose reduction of tralokinumab "
        + "in patients with atopic dermatitis using machine learning "
        + "clear almost clear objectives background methods results "
    )
    assert SOURCE_OVERLAY in detect_source_overlay(page)
    assert detect_source_overlay("仅有中文摘要背景方法结果结论。") == []
