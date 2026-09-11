# SPDX-License-Identifier: MPL-2.0
"""PLAN-045c：IL 标记消毒与叠印检测。"""
from __future__ import annotations

from qyunslation.structure.text_sanitize import (
    IL_MARKUP_LEAK,
    SOURCE_OVERLAY,
    detect_source_overlay,
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


def test_sanitize_marks_uncleared_leak():
    # 畸形残留无法完全剥掉时记 IL_MARKUP_LEAK
    leftover = "患者<span"
    cleaned, codes = sanitize_translated_text(leftover)
    assert has_il_markup_leak(cleaned) or IL_MARKUP_LEAK in codes


def test_overlay_detection_warns_on_mixed_residue():
    page = (
        "背景 曲罗芦单抗是一种抗白细胞介素-13单抗。" * 3
        + " Predicting successful dose reduction of tralokinumab "
        + "in patients with atopic dermatitis using machine learning "
        + "clear almost clear objectives background methods results "
    )
    assert SOURCE_OVERLAY in detect_source_overlay(page)
    assert detect_source_overlay("仅有中文摘要背景方法结果结论。") == []
