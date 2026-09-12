# SPDX-License-Identifier: MPL-2.0
"""PLAN-046a：图内字号上限 + 试排跳过。"""
from __future__ import annotations

import numpy as np

from qyunslation.extensions.image_translate import (
    FIGURE_TIER_MAX_PX,
    FIGURE_TIER_MIN_PX,
    _assign_tier_sizes,
    _mark_unfittable_redraw,
)


def test_figure_tier_max_caps_assigned():
    # 高窄竖排框：墨迹高很大，估字号会飙到 100+；应被 MAX 卡住
    boxes = [[0, 0, 28, 200, "Responders", 0.9]]
    styles = [{"bg_bgr": (255, 255, 255), "bold": False}]
    texts = ["Responders (%)"]
    finals = ["应答者 (%)"]
    redraw = [True]
    avails = [(0, 0, 28, 200)]
    orig = np.full((210, 40, 3), 255, dtype=np.uint8)
    orig[5:195, 5:22] = 0
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
    assert meta["assigned"][0] <= FIGURE_TIER_MAX_PX
    assert meta["assigned"][0] >= FIGURE_TIER_MIN_PX


def test_mark_unfittable_skips_non_outlier():
    boxes = [[0, 0, 40, 20, "long", 0.9]]
    styles = [{"bg_bgr": (255, 255, 255), "bold": False}]
    finals = ["一段很长很长很长很长很长的中文译文塞不进这个窄框"]
    redraw = [True]
    avails = [(0, 0, 40, 20)]
    assigned = [48]
    skipped = _mark_unfittable_redraw(
        boxes=boxes,
        finals=finals,
        redraw=redraw,
        avails=avails,
        assigned=assigned,
        styles=styles,
        font_regular=None,
        font_bold=None,
        outliers=[],
    )
    assert skipped == [1]
    assert redraw[0] is False
