"""PLAN-083d：表内角标、分组表头、深色表头底、脚注不进表、Helvetica 字形边界。"""
from __future__ import annotations

from pathlib import Path

import pytest

from qyunslation.structure import table_cell_policy as policy
from qyunslation.structure.table_cell_policy import (
    has_script_runs,
    restore_footnote_markers,
    set_script_pairs,
    split_script_runs,
    strip_footnote_markers,
)

CM512 = next(iter(sorted(Path("var/pipeline/runs").glob("*/gen-1/input/09-LIT-2026-CM512-Trial.pdf"))), None)


@pytest.fixture(autouse=True)
def _reset_scripts():
    set_script_pairs(None)
    yield
    set_script_pairs(None)


def test_script_runs_are_off_by_default_and_on_for_literature():
    assert split_script_runs("Cmax, mg/mL") == [("Cmax, mg/mL", "")]
    assert not has_script_runs("Cmax")
    set_script_pairs([])
    assert split_script_runs("Cmax, mg/mL") == [("C", ""), ("max", "sub"), (", mg/mL", "")]
    assert split_script_runs("AUC0–τ, 天") == [("AUC", ""), ("0–τ", "sub"), (", 天", "")]
    assert split_script_runs("t1/2z, 天")[1] == ("1/2z", "sub")
    assert split_script_runs("Vz/F, L")[:2] == [("V", ""), ("z", "sub")]
    assert split_script_runs("Rac_Cmax") == [("R", ""), ("ac_Cmax", "sub")]


def test_ordinary_words_are_not_turned_into_subscripts():
    set_script_pairs([])
    for word in ("Quiz", "maximum Cmaxima", "Tmaximum", "Hz"):
        assert not has_script_runs(word)


def test_real_source_pairs_extend_the_defaults():
    set_script_pairs([("mg", "a", "sup")])
    assert split_script_runs("150 mga (n=8)") == [("150 ", ""), ("mg", ""), ("a", "sup"), (" (n=8)", "")]


def test_footnote_marker_is_taken_out_before_translation_and_put_back_after():
    pairs = [("mg", "a", "sup"), ("mg", "b", "sup")]
    clean, removed = strip_footnote_markers("CM512–150 mga (n = 8)", pairs)
    assert clean == "CM512–150 mg (n = 8)" and removed == [("mg", "a")]
    assert restore_footnote_markers("CM512–150 mg (n=8)", removed) == "CM512–150 mga (n=8)"
    assert restore_footnote_markers("没有基名", removed) == "没有基名"
    # 数字角标不当脚注标记
    assert strip_footnote_markers("mg1", [("mg", "1", "sup")])[1] == []


def test_helvetica_only_for_latin1_so_en_dash_goes_to_the_cjk_font():
    from qyunslation.structure.table_writeback import _helv_has

    assert _helv_has("µ") and _helv_has("±") and _helv_has("²")
    assert not _helv_has("–") and not _helv_has("≥") and not _helv_has("’")


def _painted_spans(page):
    return [
        sp
        for block in page.get_text("dict")["blocks"]
        for line in block.get("lines", [])
        for sp in line["spans"]
        if sp["text"].strip()
    ]


def test_paint_cell_draws_subscript_smaller_and_white_ink_on_dark_fill():
    import pymupdf

    from qyunslation.structure import table_writeback as tw
    from qyunslation.structure.models import BoundingBox

    doc = pymupdf.open()
    page = doc.new_page(width=300, height=200)
    page.draw_rect(pymupdf.Rect(10, 10, 140, 40), color=(0.4, 0.45, 0.5), fill=(0.4, 0.45, 0.5))
    tw.snapshot_fills(page)
    set_script_pairs([])
    tw.prepare_embedded_font(["Cmax, 小时"])
    tw.paint_cell(page, BoundingBox(x0=10, y0=10, x1=140, y1=40), "Cmax, 小时", bold=False, font_size=9.0)
    spans = _painted_spans(page)
    sizes = {sp["text"]: round(sp["size"], 1) for sp in spans}
    assert sizes.get("max") is not None and sizes["max"] < sizes["C"]
    assert all(sp["color"] == 0xFFFFFF for sp in spans)


def test_plain_cell_keeps_black_ink_on_white():
    import pymupdf

    from qyunslation.structure import table_writeback as tw
    from qyunslation.structure.models import BoundingBox

    doc = pymupdf.open()
    page = doc.new_page(width=300, height=200)
    tw.snapshot_fills(page)
    tw.paint_cell(page, BoundingBox(x0=10, y0=10, x1=140, y1=40), "Total", bold=False, font_size=9.0)
    assert all(sp["color"] == 0 for sp in _painted_spans(page))


@pytest.mark.skipif(CM512 is None, reason="CM512 样张不在本机")
def test_cm512_group_header_filled_header_and_footnotes():
    import pymupdf

    from qyunslation.structure.table_rebuild import rebuild_from_page

    doc = pymupdf.open(CM512)
    ae = rebuild_from_page(doc[5], (49.0, 88.0, 545.4, 555.6))
    assert ae.ok and ae.n_header_rows == 2
    assert any("SAD" in c for c in ae.rows[0])
    assert any("placebo" in c and "n = 8" in c for c in ae.rows[1])  # 列表头各行合并成一格，不拆成三行
    assert all(not (r[0] or "").startswith(("n (%), number", "*The most")) for r in ae.rows)  # 脚注不进表
    assert ae.table_bottom and ae.table_bottom < 555.6
    pk = rebuild_from_page(doc[6], (49.0, 88.0, 545.4, 258.9))
    assert ("C", "max", "sub") in pk.script_pairs
