"""PLAN-028d: Tier-3 must reuse one page analysis and avoid legacy tables."""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

from qyunslation.structure import PdfStructureScanner
from qyunslation.structure import captions as captions_module
from qyunslation.structure import scan_pdf as scan_pdf_module

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import pdf_figure_crop  # noqa: E402


def _write_text_pdf(path: Path) -> None:
    document = pymupdf.open()
    try:
        page = document.new_page()
        page.insert_textbox(
            pymupdf.Rect(72, 72, 500, 180),
            "A paragraph of body text long enough to survive the body block "
            "filter and exercise Tier-3 page analysis without any figures.",
        )
        document.save(path)
    finally:
        document.close()


def test_scanner_never_calls_legacy_table_detection(tmp_path, monkeypatch):
    source = tmp_path / "text.pdf"
    _write_text_pdf(source)

    def fail_if_called(_page):
        raise AssertionError("modern Tier-3 must not call page.find_tables()")

    monkeypatch.setattr(pdf_figure_crop, "table_rects", fail_if_called)

    manifest = PdfStructureScanner().scan(source)

    assert manifest.extensions["pages_scanned"] == 1
    assert manifest.extensions["truncated"] is False
    assert "SCAN_PAGE_FAILED" not in {issue.code for issue in manifest.issues}


def test_scanner_extracts_caption_anchors_once_per_page(tmp_path, monkeypatch):
    source = tmp_path / "caption.pdf"
    _write_text_pdf(source)
    calls = 0
    original = captions_module.caption_anchors

    def counted(page):
        nonlocal calls
        calls += 1
        return original(page)

    monkeypatch.setattr(captions_module, "caption_anchors", counted)
    monkeypatch.setattr(scan_pdf_module, "caption_anchors", counted)

    manifest = PdfStructureScanner().scan(source)

    assert manifest.extensions["pages_scanned"] == 1
    assert calls == 1


def test_figure_helpers_accept_precomputed_page_evidence():
    document = pymupdf.open(ROOT / "tests/fixtures/structure/reference/nature_comm_53384.pdf")
    try:
        page = document[2]
        anchors = captions_module.caption_anchors(page)
        profile = pdf_figure_crop.page_caption_profile(page, anchors=anchors)
        drawings = page.get_drawings()
        raw_blocks = page.get_text("blocks")

        regions = pdf_figure_crop.labeled_figure_regions(
            page,
            profile=profile,
            tables=[],
            drawings=drawings,
            text_blocks=raw_blocks,
        )
    finally:
        document.close()

    assert regions
