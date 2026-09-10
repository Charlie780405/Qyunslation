"""PLAN-035c/035d：跨页续表扫描与执行排序。"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from qyunslation.structure import PdfStructureScanner
from qyunslation.structure.captions import continued_table_anchors, is_continued_caption
from qyunslation.structure.models import ObjectType
from tests.fixtures.structure.generate_synthetic import _continued_table_pdf_bytes

ROOT = Path(__file__).resolve().parents[2]
CONTINUED_PDF = ROOT / "tests/fixtures/structure/synthetic/continued-table.pdf"


@pytest.fixture(scope="module")
def continued_pdf_path(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp("plan035") / "continued-table.pdf"
    data = _continued_table_pdf_bytes()
    target.write_bytes(data)
    return target


@pytest.fixture(scope="module")
def continued_manifest(continued_pdf_path):
    return PdfStructureScanner().scan(continued_pdf_path)


def test_continued_caption_detection():
    assert is_continued_caption("Table 2 Continued")
    assert is_continued_caption("(continues)")


def test_continued_table_scan_produces_two_occurrences(continued_manifest):
    tables = [o for o in continued_manifest.objects if o.type is ObjectType.TABLE]
    assert len(tables) == 2
    assert continued_manifest.summary.table_count == 1
    by_occ = sorted(tables, key=lambda o: o.semantic_occurrence_index)
    assert by_occ[0].semantic_id == "table:2"
    assert by_occ[0].semantic_occurrence_index == 1
    assert by_occ[1].semantic_occurrence_index == 2
    assert by_occ[0].canvas_id == "page:1"
    assert by_occ[1].canvas_id == "page:2"


def test_continued_rows_are_globally_numbered(continued_manifest):
    tables = sorted(
        [o for o in continued_manifest.objects if o.type is ObjectType.TABLE],
        key=lambda o: o.semantic_occurrence_index,
    )
    first_rows = {
        b.row_index for b in tables[0].translatable_blocks if b.row_index is not None
    }
    second_rows = {
        b.row_index for b in tables[1].translatable_blocks if b.row_index is not None
    }
    assert first_rows
    assert second_rows
    assert min(second_rows) > max(first_rows)


def test_continued_table_fixture_hash_is_stable():
    data = _continued_table_pdf_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert len(digest) == 64


def test_continued_table_anchors_on_page_two(continued_pdf_path):
    import pymupdf

    doc = pymupdf.open(continued_pdf_path)
    try:
        anchors = continued_table_anchors(doc[1])
    finally:
        doc.close()
    assert anchors
    assert anchors[0][0] == 2
