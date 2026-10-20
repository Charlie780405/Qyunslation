# SPDX-License-Identifier: MPL-2.0
"""PLAN-080d：译后让下划线跟随译文（用合成 PDF，不含任何真实文档内容）。"""
from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from qyunslation.structure import decoration_realign as dr

LONG = "Draft Guidance for Industry on Combination Product Risk Analysis"
SHORT = "Guidance on Product Risk Analysis"
FS = 12


def width(text: str) -> float:
    return pymupdf.get_text_length(text, fontname="helv", fontsize=FS)


def make_pdf(path: Path, *, text: str | None, y: float = 100.0, x: float = 72.0, line=None, extra=None,
             page_width: float = 612.0, line_y: float | None = None) -> Path:
    """一页：一行文字 + 一条水平线（缺省为贴着文字下沿、与文字等宽的下划线）。"""
    doc = pymupdf.open()
    page = doc.new_page(width=page_width, height=792)
    if text is not None:
        page.insert_text((x, y), text, fontname="helv", fontsize=FS)
    if line is None:
        w = width(text) if text else 100
        line = (x, x + w)
    ly = line_y if line_y is not None else y + 2.0
    page.draw_line((line[0], ly), (line[1], ly), color=(0, 0, 1), width=0.8)
    if extra:
        extra(page)
    doc.save(path)
    doc.close()
    return path


def segments(path: Path, page: int = 0) -> list[tuple[float, float, float]]:
    doc = pymupdf.open(path)
    out = []
    for seg in dr._thin_segments(doc[page]):
        out.append((round(seg.x0, 1), round(seg.x1, 1), round(seg.y, 1)))
    doc.close()
    return sorted(out)


def text_of(path: Path) -> str:
    doc = pymupdf.open(path)
    try:
        return "".join(p.get_text() for p in doc)
    finally:
        doc.close()


@pytest.fixture
def src(tmp_path):
    return make_pdf(tmp_path / "src.pdf", text=LONG)


def test_mode_defaults_to_off(monkeypatch):
    monkeypatch.delenv(dr.MODE_ENV, raising=False)
    assert dr.realign_mode() == "off"
    monkeypatch.setenv(dr.MODE_ENV, "on")
    assert dr.realign_mode() == "on"


def test_overlong_underline_is_trimmed_to_the_translated_text(tmp_path, src):
    # 译文重排后文字变短，线仍是原文宽度（BabelDOC 不改矢量图形）
    out = make_pdf(tmp_path / "out.pdf", text=SHORT, line=(72, 72 + width(LONG)))
    report = dr.realign_pdf(src, out, tmp_path / "res.pdf")
    (x0, x1, _y), = segments(tmp_path / "res.pdf")
    assert report.trimmed == 1
    assert x0 == pytest.approx(72, abs=1) and x1 == pytest.approx(72 + width(SHORT), abs=2)
    assert text_of(tmp_path / "res.pdf") == text_of(out)


def test_underline_that_already_fits_is_kept(tmp_path, src):
    out = make_pdf(tmp_path / "out.pdf", text=LONG)
    before = segments(out)
    report = dr.realign_pdf(src, out, tmp_path / "res.pdf")
    assert report.kept == 1 and report.trimmed == 0
    assert segments(tmp_path / "res.pdf") == before


def test_dangling_underline_with_no_text_nearby_is_removed(tmp_path, src):
    out = make_pdf(tmp_path / "out.pdf", text=None, line=(72, 72 + width(LONG)), line_y=102.0)
    report = dr.realign_pdf(src, out, tmp_path / "res.pdf")
    assert report.removed == 1
    assert segments(tmp_path / "res.pdf") == []


def test_underline_is_moved_to_text_that_shifted_down(tmp_path, src):
    out = make_pdf(tmp_path / "out.pdf", text=SHORT, y=106.0, line=(72, 72 + width(LONG)), line_y=102.0)
    report = dr.realign_pdf(src, out, tmp_path / "res.pdf")
    (_x0, _x1, y), = segments(tmp_path / "res.pdf")
    assert report.moved == 1
    assert 106.0 <= y <= 110.5  # 落在新文字行的下沿附近


def test_remnant_shorter_than_a_character_is_removed(tmp_path, src):
    # 原线盖的是一段译文里已不存在的文字（如网址）；与译文只剩一个标点的重叠，不应留一小截线
    out = make_pdf(tmp_path / "out.pdf", text=".", x=72 + width(LONG) - 3, line=(72, 72 + width(LONG)))
    report = dr.realign_pdf(src, out, tmp_path / "res.pdf")
    assert report.removed == 1
    assert segments(tmp_path / "res.pdf") == []


def test_table_borders_are_not_treated_as_underlines(tmp_path):
    def grid(page):
        page.draw_line((72, 90), (72, 110), width=0.8)
        page.draw_line((72 + width(LONG), 90), (72 + width(LONG), 110), width=0.8)

    src = make_pdf(tmp_path / "src.pdf", text=LONG, extra=grid)
    out = make_pdf(tmp_path / "out.pdf", text=SHORT, line=(72, 72 + width(LONG)), extra=grid)
    before = segments(out)
    report = dr.realign_pdf(src, out, tmp_path / "res.pdf")
    assert report.candidates == 0 and report.skipped_grid == 1
    assert segments(tmp_path / "res.pdf") == before


def test_separator_much_wider_than_text_is_left_alone(tmp_path):
    src = make_pdf(tmp_path / "src.pdf", text="Page 3", line=(72, 540))
    out = make_pdf(tmp_path / "out.pdf", text="Page 3", line=(72, 540))
    report = dr.realign_pdf(src, out, tmp_path / "res.pdf")
    assert report.candidates == 0
    assert segments(tmp_path / "res.pdf") == segments(out)


def test_erase_is_skipped_when_other_graphics_share_the_spot(tmp_path, src):
    def shading(page):  # 一块贴着线的底纹：触碰即删会把它一起删掉
        page.draw_rect(pymupdf.Rect(60, 98, 300, 103.5), color=None, fill=(0.9, 0.9, 0.9))

    out = make_pdf(tmp_path / "out.pdf", text=SHORT, line=(72, 72 + width(LONG)), extra=shading)
    doc = pymupdf.open(out)
    rects_before = [tuple(round(v, 1) for v in d["rect"]) for d in doc[0].get_drawings() if d["rect"].height > 3]
    doc.close()
    report = dr.realign_pdf(src, out, tmp_path / "res.pdf")
    doc = pymupdf.open(tmp_path / "res.pdf")
    rects_after = [tuple(round(v, 1) for v in d["rect"]) for d in doc[0].get_drawings() if d["rect"].height > 3]
    doc.close()
    assert report.skipped_shared == 1
    assert rects_after == rects_before  # 底纹还在，线保持原样


def test_dual_layout_right_half_is_aligned_with_offset(tmp_path, src):
    # dual = 左原文右译文，页宽 2 倍；译文半幅的 x 整体加页宽
    off = 612.0
    out = make_pdf(tmp_path / "out.pdf", text=SHORT, x=72 + off, page_width=1224.0,
                   line=(72 + off, 72 + off + width(LONG)))
    report = dr.realign_pdf(src, out, tmp_path / "res.pdf")
    (x0, x1, _y), = segments(tmp_path / "res.pdf")
    assert report.trimmed == 1
    assert x0 == pytest.approx(72 + off, abs=1) and x1 == pytest.approx(72 + off + width(SHORT), abs=2)


def test_failure_keeps_the_original_file_usable(tmp_path, src, monkeypatch):
    out = make_pdf(tmp_path / "out.pdf", text=SHORT, line=(72, 72 + width(LONG)))
    monkeypatch.setattr(dr, "plan_line", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    report = dr.realign_pdf(src, out, tmp_path / "res.pdf")
    assert report.failed_pages == [1]
    assert segments(tmp_path / "res.pdf") == segments(out)


def test_page_count_mismatch_is_skipped_not_misaligned(tmp_path, src):
    """交替页的 dual（页数翻倍）等情形页与页对不上：宁可不处理，也不能把线画到别的页上。"""
    long = pymupdf.get_text_length(LONG, fontname="helv", fontsize=FS)
    one = make_pdf(tmp_path / "one.pdf", text=SHORT, line=(72, 72 + long))
    doc = pymupdf.open()
    doc.insert_pdf(pymupdf.open(one))
    doc.insert_pdf(pymupdf.open(one))
    two = tmp_path / "two.pdf"
    doc.save(two)
    report = dr.realign_pdf(src, two, tmp_path / "res.pdf")
    assert report.skipped_reason and "page_count_mismatch" in report.skipped_reason
    assert report.trimmed == report.removed == report.moved == 0
    assert segments(tmp_path / "res.pdf", 0) == segments(two, 0)
    assert segments(tmp_path / "res.pdf", 1) == segments(two, 1)
