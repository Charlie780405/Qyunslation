from __future__ import annotations

import sys
from pathlib import Path

import pymupdf
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from pdf_figure_crop import (  # noqa: E402
    SLIDE_MAX_AREA_FRAC,
    SLIDE_MIN_DRAWINGS,
    SLIDE_TEXT_OVERLAP,
    find_figure_regions,
    find_safe_vector_figures,
    is_slide_page,
    page_caption_profile,
)

LJAE = ROOT / "tests/fixtures/structure/reference/ljae439.pdf"
NATURE = ROOT / "tests/fixtures/structure/reference/nature_comm_53384.pdf"
SLIDE = Path(
    "/home/dev/pdf2zh/pdf2zh_files/57114032-8727-41f9-b826-b5ff40fcf733/"
    "QX027N QnA-2026.08.19-临床.pdf"
)


def _covered_figures(doc) -> set[int]:
    covered: set[int] = set()
    for page in doc:
        profile = page_caption_profile(page)
        if not find_figure_regions(page):
            continue
        for kind, num, _y, _bb in profile["figure_caps"]:
            covered.add(num)
    return covered


def test_page_caption_profile_kinds_on_nature():
    doc = pymupdf.open(NATURE)
    try:
        kinds = {i + 1: page_caption_profile(doc[i])["page_kind"] for i in range(len(doc))}
    finally:
        doc.close()
    assert kinds[4] == "pure_table"
    assert kinds[5] == "pure_table"
    assert kinds[9] == "pure_table"
    assert kinds[10] == "figure_only"
    assert kinds[3] == "figure_only"


def test_nature_figure_regions_cover_seven_and_block_table_pages():
    doc = pymupdf.open(NATURE)
    try:
        regions = [find_figure_regions(p) for p in doc]
        assert len(regions[3]) == 0
        assert len(regions[4]) == 0
        assert len(regions[8]) == 0
        total = sum(len(r) for r in regions)
        assert total == 7
        assert _covered_figures(doc) == {1, 2, 3, 4, 5, 6, 7}
    finally:
        doc.close()


def test_ljae439_figure_regions_cover_five_and_block_table_pages():
    doc = pymupdf.open(LJAE)
    try:
        tabs: set[int] = set()
        for page in doc:
            profile = page_caption_profile(page)
            tabs.update(n for k, n, _y, _b in profile["table_caps"])
            if profile["page_kind"] == "pure_table":
                assert find_figure_regions(page) == []
        assert tabs == {1, 2, 3}
        captioned = [
            len(find_figure_regions(p))
            for p in doc
            if page_caption_profile(p)["page_kind"] != "none"
        ]
        assert sum(captioned) == 5
        assert _covered_figures(doc) == {1, 2, 3, 4, 5}
    finally:
        doc.close()


def test_legacy_find_safe_vector_figures_unchanged_on_nature():
    doc = pymupdf.open(NATURE)
    try:
        n = sum(len(find_safe_vector_figures(p)) for p in doc)
    finally:
        doc.close()
    assert n == 12


@pytest.mark.skipif(not SLIDE.is_file(), reason="slide sample missing")
def test_slide_profile_still_twelve_regions():
    doc = pymupdf.open(SLIDE)
    try:
        assert all(is_slide_page(p) for p in doc)
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
        )
        caption_n = sum(len(find_figure_regions(p)) for p in doc)
    finally:
        doc.close()
        assert profile_n == 12
        assert caption_n == 8
