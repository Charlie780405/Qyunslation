"""PLAN-033e：当前页 300 DPI，进度用图/表计数。"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pdf_preview_pages import (  # noqa: E402
    PREVIEW_HI_DPI,
    PREVIEW_LO_DPI,
    page_pixel_size,
    render_preview_pages,
)
from qyunslation.structure.progress import format_from_manifest, format_semantic_progress
from qyunslation.structure.models import ManifestSummary


def _three_page(tmp_path: Path) -> Path:
    src = tmp_path / "pages.pdf"
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page(width=612, height=792)
    doc.save(src)
    doc.close()
    return src


def test_only_current_page_is_300_dpi(tmp_path):
    src = _three_page(tmp_path)
    dest = tmp_path / "out"
    paths = render_preview_pages(src, current_page=2, dest_dir=dest)
    assert set(paths) == {1, 2, 3}
    sizes = {n: Image.open(p).size for n, p in paths.items()}
    doc = pymupdf.open(src)
    try:
        hi = page_pixel_size(doc[1], PREVIEW_HI_DPI)
        lo = page_pixel_size(doc[0], PREVIEW_LO_DPI)
    finally:
        doc.close()
    assert sizes[2] == hi
    assert sizes[1] == lo
    assert sizes[3] == lo
    assert sizes[2][1] == round(792 * 300 / 72)


def test_semantic_progress_uses_figure_table_counts():
    assert format_semantic_progress(1, 2, 2, 4) == "已处理 图 1/2 · 表 2/4"

    class _M:
        summary = ManifestSummary(figure_count=2, table_count=4)

    assert "图" in format_from_manifest(_M(), 0, 10)
    assert format_from_manifest(_M(), 10, 10) == "已处理 图 2/2 · 表 4/4"
