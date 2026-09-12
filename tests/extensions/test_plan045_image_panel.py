# SPDX-License-Identifier: MPL-2.0
"""PLAN-045d：插图面板字母同级与 k 不含 panel。"""
from __future__ import annotations

import numpy as np

from qyunslation.extensions.image_translate import (
    FIGURE_TIER_MIN_PX,
    PANEL_TIER,
    TIER_K_FLOOR,
    _assign_tier_sizes,
    _assign_tiers,
    _is_panel_letter,
)


def test_panel_letter_detection():
    assert _is_panel_letter("A")
    assert _is_panel_letter("b.")
    assert _is_panel_letter(" C) ")
    assert not _is_panel_letter("Analysis")
    assert not _is_panel_letter("IGA")


def test_assign_tiers_forces_panel_group():
    boxes = [
        [0, 0, 20, 20, "A", 0.9],
        [0, 40, 20, 60, "B", 0.9],
        [40, 0, 200, 30, "Title", 0.9],
    ]
    styles = [
        {"bg_bgr": (0, 128, 64)},  # green
        {"bg_bgr": (255, 255, 255)},  # white
        {"bg_bgr": (255, 255, 255)},
    ]
    texts = ["A", "B", "Title text"]
    tiers = _assign_tiers(boxes, styles, texts=texts)
    assert tiers[0] == PANEL_TIER
    assert tiers[1] == PANEL_TIER
    assert tiers[2] != PANEL_TIER


def test_panel_sizes_equal_and_k_floor(monkeypatch):
    # 合成：两个面板字母 + 一个挤框长句
    boxes = [
        [0, 0, 30, 30, "A", 0.9],
        [0, 50, 30, 80, "B", 0.9],
        [40, 0, 90, 20, "long", 0.9],
    ]
    styles = [
        {"bg_bgr": (0, 100, 0), "bold": False},
        {"bg_bgr": (255, 255, 255), "bold": False},
        {"bg_bgr": (255, 255, 255), "bold": False},
    ]
    texts = ["A", "B", "very long phrase that will not fit"]
    finals = texts[:]
    redraw = [True, True, True]
    avails = [(0, 0, 30, 30), (0, 50, 30, 80), (40, 0, 90, 20)]
    orig = np.full((100, 100, 3), 255, dtype=np.uint8)
    # 绿底 + 白底上画黑块当作墨迹
    orig[2:28, 2:28] = (0, 100, 0)
    orig[5:25, 5:25] = (0, 0, 0)
    orig[55:75, 5:25] = (0, 0, 0)
    orig[2:18, 42:88] = (0, 0, 0)

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
    assert meta["tiers"][0] == PANEL_TIER
    assert meta["tiers"][1] == PANEL_TIER
    assert meta["assigned"][0] == meta["assigned"][1]
    assert meta["k"] >= TIER_K_FLOOR


def test_small_tier_not_shrunk_below_floor(monkeypatch):
    boxes = [
        [0, 0, 80, 40, "title", 0.9],
        [0, 50, 40, 62, "tiny", 0.9],
    ]
    styles = [
        {"bg_bgr": (255, 255, 255), "bold": False},
        {"bg_bgr": (230, 245, 230), "bold": False},
    ]
    texts = ["Study design title", "n"]
    finals = texts[:]
    redraw = [True, True]
    avails = [(0, 0, 80, 40), (0, 50, 40, 62)]
    orig = np.full((80, 90, 3), 255, dtype=np.uint8)
    orig[4:36, 4:76] = 0
    orig[52:60, 4:20] = 0
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
    assert meta["assigned"][1] >= FIGURE_TIER_MIN_PX
