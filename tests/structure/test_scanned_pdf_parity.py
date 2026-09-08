"""PLAN-030d Task 9：原生 / 扫描 / 混合 PDF 的逐页判定与路径对齐。"""
from __future__ import annotations

import time
from pathlib import Path

import pymupdf
import pytest

from qyunslation.structure import PdfStructureScanner
from qyunslation.structure.models import (
    ExecutionStatus,
    ProcessingMode,
    Representation,
)
from qyunslation.structure.representation import (
    document_representation,
    needs_ocr,
    page_representation,
)

ROOT = Path(__file__).resolve().parents[2]
from tests.structure.sample_paths import (
    SCANNED_PAGE_COUNT,
    both_ocr,
    both_scanned,
)

LJAE = ROOT / "tests/fixtures/structure/reference/ljae439.pdf"


def _scanned_page(doc):
    """整页图、无文字层——扫描件的形态。"""
    page = doc.new_page()
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 80))
    pixmap.clear_with(200)
    page.insert_image(page.rect, pixmap=pixmap)
    return page


def _native_page(doc):
    page = doc.new_page()
    page.insert_text(
        (72, 100),
        "A native text page with enough characters to have a real text layer.",
    )
    return page


def _modes(path: Path) -> list[Representation]:
    doc = pymupdf.open(path)
    try:
        return [page_representation(page) for page in doc]
    finally:
        doc.close()


def test_native_document_is_native_on_every_page():
    modes = _modes(LJAE)

    assert set(modes) == {Representation.NATIVE_TEXT}
    assert document_representation(modes) is Representation.NATIVE_TEXT
    assert needs_ocr(modes) is False


@both_scanned
def test_scanned_document_is_scanned_on_every_page(scanned_pdf):
    modes = _modes(scanned_pdf)

    assert set(modes) == {Representation.SCANNED}
    assert document_representation(modes) is Representation.SCANNED
    assert needs_ocr(modes) is True


@both_ocr
def test_ocr_output_is_hybrid_not_native(ocr_pdf):
    """OCR 后仍压着整页扫描图，不能当作原生文字件。"""
    modes = _modes(ocr_pdf)

    assert set(modes) == {Representation.HYBRID}
    assert document_representation(modes) is Representation.HYBRID


def test_mixed_document_is_judged_per_page(tmp_path):
    """部分页扫描的混合件不得整档一刀切。"""
    path = tmp_path / "mixed.pdf"
    doc = pymupdf.open()
    try:
        _native_page(doc)
        _native_page(doc)
        _scanned_page(doc)
        doc.save(path)
    finally:
        doc.close()

    modes = _modes(path)

    assert modes == [
        Representation.NATIVE_TEXT,
        Representation.NATIVE_TEXT,
        Representation.SCANNED,
    ]
    assert document_representation(modes) is Representation.HYBRID
    assert needs_ocr(modes) is True


def test_whole_document_char_gate_would_miss_the_scanned_page(tmp_path):
    """hpd_ocr.pdf_needs_hpd 看整档字符数，混合件会被判成不需要 OCR。"""
    path = tmp_path / "mixed.pdf"
    doc = pymupdf.open()
    try:
        _native_page(doc)
        _native_page(doc)
        _scanned_page(doc)
        doc.save(path)
    finally:
        doc.close()

    doc = pymupdf.open(path)
    try:
        whole_doc_chars = sum(len((p.get_text() or "").strip()) for p in doc)
    finally:
        doc.close()

    assert whole_doc_chars >= 80  # 整档门槛判定：不需要 OCR
    assert needs_ocr(_modes(path)) is True  # 逐页判定：第三页需要


def test_manifest_records_representation_for_native():
    manifest = PdfStructureScanner().scan(LJAE)

    assert manifest.extensions["document_representation"] == "NATIVE_TEXT"
    assert manifest.extensions["needs_ocr"] is False
    assert manifest.document.selected_mode is ProcessingMode.NATIVE


@both_scanned
def test_manifest_marks_scanned_document_hybrid(scanned_pdf):
    manifest = PdfStructureScanner().scan(scanned_pdf)

    assert manifest.extensions["document_representation"] == "SCANNED"
    assert manifest.extensions["needs_ocr"] is True
    assert manifest.document.selected_mode is ProcessingMode.HYBRID


@both_scanned
def test_pages_requiring_ocr_are_listed(scanned_pdf):
    manifest = PdfStructureScanner().scan(scanned_pdf)

    issues = [i for i in manifest.issues if i.code == "PAGES_REQUIRE_OCR"]
    assert len(issues) == 1
    assert issues[0].details["pages"] == list(range(1, SCANNED_PAGE_COUNT + 1))


def test_page_representations_are_recorded_per_page():
    manifest = PdfStructureScanner().scan(LJAE)
    per_page = manifest.extensions["page_representations"]

    assert len(per_page) == 10
    assert set(per_page.values()) == {"NATIVE_TEXT"}


@both_scanned
def test_scanned_path_leaves_no_pending_objects(scanned_pdf):
    manifest = PdfStructureScanner().scan(scanned_pdf)

    pending = [
        o for o in manifest.objects if o.execution_status is ExecutionStatus.PENDING
    ]
    assert pending == []


@both_scanned
def test_scanning_stays_well_inside_the_prescan_budget(scanned_pdf):
    """20 页扫描件必须远低于 Tier-3 的 25s 预算。

    早期实现用 get_image_rects() 量图片覆盖，这一份要 17s；改走 get_text("dict")
    的图像块后降到亚秒级。
    """
    started = time.monotonic()
    PdfStructureScanner().scan(scanned_pdf)
    elapsed = time.monotonic() - started

    assert elapsed < 10.0


def test_blank_page_without_text_is_treated_as_scanned(tmp_path):
    """没有文字层就得走 OCR，宁可多判也不能漏判。"""
    doc = pymupdf.open()
    try:
        doc.new_page()
        modes = [page_representation(page) for page in doc]
    finally:
        doc.close()

    assert modes == [Representation.SCANNED]


def test_document_representation_of_empty_page_list():
    assert document_representation([]) is Representation.NATIVE_TEXT


def test_mixed_scanned_and_hybrid_is_hybrid():
    modes = [Representation.SCANNED, Representation.HYBRID]

    assert document_representation(modes) is Representation.HYBRID


def test_requested_mode_is_preserved_while_selected_reflects_reality():
    manifest = PdfStructureScanner().scan(
        LJAE, processing_mode=ProcessingMode.NATIVE
    )

    assert manifest.document.requested_mode is ProcessingMode.NATIVE
    assert manifest.document.selected_mode is ProcessingMode.NATIVE
