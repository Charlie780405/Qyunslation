# SPDX-License-Identifier: MPL-2.0
"""PLAN-046d：竖排旋转、面板字母放宽、OCR 垃圾门禁。"""
from __future__ import annotations

import numpy as np

from qyunslation.extensions.image_translate import (
    FIGURE_TIER_MAX_PX,
    PANEL_TIER,
    ROTATED_TIER,
    _assign_tier_sizes,
    _assign_tiers,
    _is_ocr_garbage,
    _is_panel_letter,
    _is_rotated_axis_box,
)


def test_panel_letter_paren_and_confusion():
    assert _is_panel_letter("(a)")
    assert _is_panel_letter("(C)")
    assert _is_panel_letter("B")
    assert _is_panel_letter("8")  # OCR→B
    assert not _is_panel_letter("Analysis")


def test_rotated_axis_detection():
    box = [0, 0, 20, 180, "Responders (%)", 0.9]
    assert _is_rotated_axis_box(box, "Responders (%)")
    assert not _is_rotated_axis_box([0, 0, 200, 20, "x", 0.9], "Time (weeks)")


def test_ocr_garbage():
    assert _is_ocr_garbage("F08", 0.55)
    # PLAN-047f：F08 类短串与 score 无关，一律垃圾
    assert _is_ocr_garbage("F08", 0.95)
    assert not _is_ocr_garbage("Q2W", 0.6)
    assert not _is_ocr_garbage("应答者", 0.5)


def test_rotated_tier_uses_short_edge_size():
    boxes = [[0, 0, 24, 200, "Responders", 0.9]]
    styles = [{"bg_bgr": (255, 255, 255), "bold": False, "rotated": True}]
    texts = ["Responders (%)"]
    finals = ["应答者 (%)"]
    redraw = [True]
    avails = [(0, 0, 24, 200)]
    orig = np.full((210, 40, 3), 255, dtype=np.uint8)
    orig[5:195, 5:20] = 0
    meta = _assign_tier_sizes(
        boxes=boxes,
        texts=texts,
        finals=finals,
        redraw=redraw,
        styles=styles,
        avails=avails,
        orig=orig,
        font_regular=None,
        font_bold=None,
    )
    assert meta["tiers"][0] == ROTATED_TIER
    assert meta["assigned"][0] <= FIGURE_TIER_MAX_PX
    # 短边估字号应远小于旧逻辑的 120+
    assert meta["assigned"][0] <= 30


def test_assign_tiers_panel_paren():
    boxes = [[0, 0, 20, 20, "(a)", 0.9], [0, 40, 20, 60, "B", 0.9]]
    styles = [{"bg_bgr": (0, 0, 0)}, {"bg_bgr": (255, 255, 255)}]
    tiers = _assign_tiers(boxes, styles, texts=["(a)", "B"])
    assert tiers[0] == PANEL_TIER
    assert tiers[1] == PANEL_TIER
