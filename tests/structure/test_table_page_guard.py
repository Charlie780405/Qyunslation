from __future__ import annotations

import sys
from pathlib import Path

import pymupdf
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from doc_image_prescan import scan_pdf_tier3  # noqa: E402
from pdf_figure_crop import (  # noqa: E402
    SLIDE_MAX_AREA_FRAC,
    SLIDE_MIN_DRAWINGS,
    SLIDE_TEXT_OVERLAP,
    find_figure_regions,
    find_safe_vector_figures,
    is_slide_page,
    translatable_regions,
)

NATURE = ROOT / "tests/fixtures/structure/reference/nature_comm_53384.pdf"
SLIDE = Path(
    "/home/dev/pdf2zh/pdf2zh_files/57114032-8727-41f9-b826-b5ff40fcf733/"
    "QX027N QnA-2026.08.19-临床.pdf"
)


def test_nature_table2_page_has_no_ocr_regions():
    doc = pymupdf.open(NATURE)
    try:
        page = doc[4]
        assert find_figure_regions(page) == []
        assert translatable_regions(page) == []
    finally:
        doc.close()


def test_imgtr_strategy_b_uses_the_shared_region_dispatcher():
    src = (SCRIPTS / "pdf_image_translate.py").read_text(encoding="utf-8")
    assert "translatable_regions(page, exclude_rects=exclude)" in src
    assert "SLIDE_MIN_DRAWINGS" not in src


@pytest.mark.skipif(not SLIDE.is_file(), reason="slide sample missing")
def test_slide_pages_keep_plan029b_profile_count():
    doc = pymupdf.open(SLIDE)
    try:
        profile_n = sum(
            len(
                find_safe_vector_figures(
                    p,
                    tables=[],
                    text_overlap_max=SLIDE_TEXT_OVERLAP,
                    max_area_frac=SLIDE_MAX_AREA_FRAC,
                    min_drawings=SLIDE_MIN_DRAWINGS,
                )
            )
            for p in doc
            if is_slide_page(p)
        )
        dispatched_n = sum(len(translatable_regions(p)) for p in doc)
    finally:
        doc.close()
    assert profile_n == 12
    assert dispatched_n == 12


@pytest.mark.skipif(not SLIDE.is_file(), reason="slide sample missing")
def test_slide_prescan_matches_execution_regions():
    """PLAN-027 不变量 4：幻灯无题注，预扫描不得报 0 而执行嵌 12 张。"""

    doc = pymupdf.open(SLIDE)
    try:
        execution_n = sum(len(translatable_regions(p)) for p in doc)
    finally:
        doc.close()

    result = scan_pdf_tier3(SLIDE)

    assert result.translatable_count == execution_n
    # PLAN-030d：幻灯确实没有题注，12 处区域记在无编号计数下，不伪造 Figure 编号
    assert result.figure_caption_count == 0
    assert result.unnumbered_count == execution_n
    assert result.table_caption_count == 0
