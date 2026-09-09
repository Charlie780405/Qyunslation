"""PLAN-033k：role-aware fitter 与对象级 QC。"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from qyunslation.extensions.image_translate import (
    QC_INK_MIN,
    _c3_is_blank,
    _c3_window,
    _c6_em,
    _font_below_warned,
    _line_guard_mask,
    _text_mask_u8,
    _wipe_remaining_source_ink,
)
from qyunslation.structure.role_fitter import (
    QC_FONT_BELOW_TARGET,
    QC_OVERFLOW,
    QC_ROLE_SIZE_DRIFT,
    QC_UNTRANSLATED,
    FitBlock,
    choose_dpi,
    fit_block,
    fit_group,
    hard_fail_codes,
)


def test_no_line_slicing_or_majority_bold_in_image_translate():
    source = Path(__file__).resolve().parents[2] / "qyunslation/extensions/image_translate.py"
    text = source.read_text(encoding="utf-8")
    assert "lines[:max_lines]" not in text
    assert "best_lines[:max_lines]" not in text
    assert "votes * 2 >= len(idxs)" not in text


def test_block_inherits_source_bold_not_tier_vote():
    bold = FitBlock("a", "figure_label", "A", "甲", 10, True, 80, 20)
    regular = FitBlock("b", "figure_label", "B", "乙", 10, False, 80, 20)
    results = fit_group([bold, regular])
    assert results[0].bold is True
    assert results[1].bold is False


def test_semantic_compact_keeps_mapping_and_numbers():
    def compact(text: str):
        return "IL-13 通路", {"白细胞介素13信号通路": "IL-13 通路"}

    block = FitBlock(
        "fig1",
        "figure_body",
        "IL-13 signaling pathway",
        "白细胞介素13信号通路激活后导致下游炎症",
        8,
        False,
        20,
        10,
    )
    result = fit_block(block, compact=compact)
    assert "IL-13" in result.text
    assert result.mapping["白细胞介素13信号通路"] == "IL-13 通路"


def test_table_roles_do_not_unify_or_drift_fail():
    wide = FitBlock("a", "table_cell", "Age", "年龄", 9, False, 80, 16)
    tiny = FitBlock("b", "table_cell", "1", "1", 9, False, 8, 20)
    results = fit_group([wide, tiny])
    assert results[0].font_size != results[1].font_size or results[0].font_size <= 9
    assert QC_ROLE_SIZE_DRIFT not in results[0].qc
    assert QC_ROLE_SIZE_DRIFT not in results[1].qc
    assert QC_ROLE_SIZE_DRIFT not in hard_fail_codes(results)


def test_small_type_raises_dpi_and_below_target_is_warning():
    block = FitBlock("fn", "figure_footnote", "note", "脚注内容需要完整保留且不能截断", 8, False, 12, 8)
    result = fit_block(block)
    assert result.dpi in {450, 600}
    assert QC_FONT_BELOW_TARGET in result.qc or result.font_size >= 5.0
    assert not result.text.endswith("...")
    assert QC_UNTRANSLATED not in result.qc


def test_overflow_is_hard_fail_untranslated_is_hard_fail():
    empty = fit_block(FitBlock("x", "figure_body", "src", "", 10, False, 40, 12))
    assert QC_UNTRANSLATED in empty.qc
    assert QC_UNTRANSLATED in hard_fail_codes([empty])
    tiny = fit_block(
        FitBlock("y", "figure_body", "src", "这段译文在极小框里必然会溢出并且不能靠截断过关", 12, False, 4, 4)
    )
    assert not tiny.text.endswith("...")
    assert tiny.overflow or QC_OVERFLOW in tiny.qc or QC_FONT_BELOW_TARGET in tiny.qc


def test_c3_prefers_draw_bbox_so_sparse_label_is_not_blank():
    """流程图短标签：大 avail 比例会假空白，draw_bbox 小窗应判有墨迹。"""
    box = [10, 10, 700, 500, "n=15"]
    avail = (0, 0, 800, 600)
    planned = {"draw_bbox": {"x1": 180, "y1": 190, "x2": 260, "y2": 214}}
    win, used = _c3_window(box, avail, planned, 800, 600)
    assert used is True
    assert win[2] - win[0] < 100
    erased = np.full((600, 800), False)
    drawn = erased.copy()
    drawn[194:210, 184:256] = True
    assert _c3_is_blank(drawn[win[1] : win[3], win[0] : win[2]], used) is False
    huge = drawn[0:600, 0:800]
    assert float(huge.mean()) < QC_INK_MIN
    assert _c3_is_blank(huge, used_draw_bbox=False) is False


def test_c3_still_flags_true_blank_even_with_draw_bbox():
    planned = {"draw_bbox": {"x1": 20, "y1": 20, "x2": 80, "y2": 40}}
    win, used = _c3_window([0, 0, 200, 200, "x"], (0, 0, 200, 200), planned, 200, 200)
    empty = np.zeros((win[3] - win[1], win[2] - win[0]), dtype=bool)
    assert used is True
    assert _c3_is_blank(empty, used) is True
    win2, used2 = _c3_window([0, 0, 200, 200, "x"], (0, 0, 200, 200), {}, 200, 200)
    assert used2 is False
    assert _c3_is_blank(np.zeros((200, 200), dtype=bool), used2) is True


def test_c6_uses_short_side_for_tall_phase_bar():
    assert _c6_em([10, 10, 50, 198]) == 40
    assert _c6_em([10, 10, 130, 46]) == 36
    assert _font_below_warned([{"code": "C6", "msg": "size=10 < 0.6*em=36"}]) is True
    assert _font_below_warned([{"code": "C5", "msg": "overflow"}]) is False


def test_line_guard_does_not_swallow_vertical_word():
    roi = np.full((180, 36, 3), 255, np.uint8)
    roi[12:168, 8:28] = 20
    tm = _text_mask_u8(roi)
    guard = _line_guard_mask(roi, (255, 255, 255), tm)
    overlap = int(((guard > 0) & (tm > 0)).sum()) if guard.size and tm.size else 0
    assert overlap < 80


def test_wipe_remaining_source_ink_clears_letter_stems():
    orig = np.full((40, 80, 3), 255, np.uint8)
    orig[12:28, 20:28] = 10
    img = orig.copy()
    img[12:20, 20:28] = 255
    n = _wipe_remaining_source_ink(
        img,
        orig,
        [[5, 5, 75, 35, "AB"]],
        [{"bg_bgr": (255, 255, 255)}],
        [True],
    )
    assert n == 1
    assert int((img[12:28, 20:28] < 200).sum()) == 0


def test_line_guard_keeps_thin_rule():
    roi = np.full((80, 160, 3), 255, np.uint8)
    roi[28:58, 20:140] = 20
    roi[10:12, 8:152] = (40, 200, 200)
    guard = _line_guard_mask(roi, (255, 255, 255))
    assert int((guard[10:12] > 0).sum()) >= 80
