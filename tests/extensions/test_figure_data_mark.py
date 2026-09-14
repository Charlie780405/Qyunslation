# SPDX-License-Identifier: MPL-2.0
"""图内孤立数据标记不并框；题注/横轴不得因覆盖率跳过。"""
from __future__ import annotations

from qyunslation.extensions.image_translate import (
    _group_vertical_runs,
    _is_isolated_data_mark,
    _is_must_draw_label,
    _is_vertical_axis_fragment,
    _mark_unfittable_redraw,
)


def test_isolated_data_marks_skip_translate():
    assert _is_isolated_data_mark("77.8")
    assert _is_isolated_data_mark("14/18")
    assert _is_isolated_data_mark("36/58")
    assert _is_isolated_data_mark("94.6%")
    assert _is_isolated_data_mark("Q2W")
    assert _is_isolated_data_mark("Q4W")
    assert _is_isolated_data_mark("100")
    assert not _is_isolated_data_mark("IGA 0/1 responders at week 12")
    assert not _is_isolated_data_mark("Time (weeks) in open-label period")


def test_vertical_fragment_rejects_bar_stack():
    assert not _is_vertical_axis_fragment("77.8")
    assert not _is_vertical_axis_fragment("14/18")
    assert not _is_vertical_axis_fragment("Q2W")
    assert not _is_vertical_axis_fragment("F08")
    assert _is_vertical_axis_fragment("Res")


def test_group_vertical_runs_does_not_merge_bar_data():
    # 图4 柱：65.5 顶、38/58 底、Q2W 轴 —— 旧逻辑并成 65.538/58Q2W
    boxes = [
        [547, 412, 633, 450, "65.5", 1.0],
        [547, 868, 647, 906, "38/58", 0.99],
        [553, 935, 638, 967, "Q2W", 0.99],
        [10, 100, 28, 140, "Cum", 0.9],
        [10, 150, 28, 190, "ula", 0.9],
        [10, 200, 28, 240, "tive", 0.9],
    ]
    texts = [b[4] for b in boxes]
    new_boxes, new_texts, members = _group_vertical_runs(boxes, texts)
    assert "65.5" in new_texts
    assert "38/58" in new_texts
    assert "Q2W" in new_texts
    assert all(
        len(m) == 1
        for m, t in zip(members, new_texts)
        if t in {"65.5", "38/58", "Q2W"}
    )
    assert not any("65.5" in t and "38/58" in t for t in new_texts)


def test_must_draw_caption_and_xaxis():
    assert _is_must_draw_label("Figure 4 Maintenance of tralokinumab")
    assert _is_must_draw_label("IGA 0/1 responders at week 12")
    assert _is_must_draw_label("Time(weeks)inopen-labelperiod")
    assert _is_must_draw_label("Patientsatriska")
    assert _is_must_draw_label("Criteria for transfer from maintenance to open-label")
    assert _is_must_draw_label("Analyses")
    assert _is_must_draw_label("Results")
    assert not _is_must_draw_label("77.8")
    assert not _is_must_draw_label("14/18")
    wide = [10, 320, 520, 344, "Time (weeks)", 0.99]
    assert _is_must_draw_label("Time (weeks) in open-label period", wide)


def test_mark_unfittable_keeps_caption_despite_low_cover():
    # 宽题注盒 + 短中文：覆盖率远低于 0.70，旧逻辑 C5 跳过
    boxes = [[0, 0, 400, 24, "Time (weeks) in open-label period", 0.9]]
    styles = [{"bg_bgr": (255, 255, 255), "bold": False}]
    finals = ["开放标签期时间（周）"]
    redraw = [True]
    avails = [(0, 0, 400, 24)]
    assigned = [22]
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
        texts=["Time (weeks) in open-label period"],
    )
    assert skipped == []
    assert redraw[0] is True
