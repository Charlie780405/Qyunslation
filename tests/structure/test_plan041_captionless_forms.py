"""PLAN-041b：无题注临床监管表单的矢量网格识别。"""
from __future__ import annotations

import os
from pathlib import Path

import pymupdf
import pytest

from qyunslation.structure.models import ContentProfile, ObjectType
from qyunslation.structure.scan_pdf import PDF_STRUCTURE_SCANNER_VERSION, PdfStructureScanner
from qyunslation.structure.tables import captionless_table_regions


def _draw_segmented_table(page, bbox, rows: int, columns: int) -> None:
    x0, y0, x1, y1 = bbox
    row_h = (y1 - y0) / rows
    col_w = (x1 - x0) / columns
    for row in range(rows):
        for column in range(columns):
            cx0 = x0 + column * col_w
            cx1 = cx0 + col_w
            cy0 = y0 + row * row_h
            cy1 = cy0 + row_h
            page.draw_rect(
                pymupdf.Rect(cx0, cy0 - 0.25, cx1, cy0 + 0.25),
                color=None,
                fill=(0, 0, 0),
            )
            page.draw_rect(
                pymupdf.Rect(cx0, cy1 - 0.25, cx1, cy1 + 0.25),
                color=None,
                fill=(0, 0, 0),
            )
            page.draw_rect(
                pymupdf.Rect(cx0 - 0.25, cy0, cx0 + 0.25, cy1),
                color=None,
                fill=(0, 0, 0),
            )
            page.draw_rect(
                pymupdf.Rect(cx1 - 0.25, cy0, cx1 + 0.25, cy1),
                color=None,
                fill=(0, 0, 0),
            )
            page.insert_text(
                (cx0 + 3, cy0 + min(row_h - 2, 11)),
                f"R{row + 1}C{column + 1}",
                fontsize=7,
            )


def _synthetic_form(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 35), "Clinical Trial Registration Form", fontsize=12)
    page.insert_text((72, 52), "Eligibility Criteria", fontsize=10)
    _draw_segmented_table(page, (72, 72, 523, 144), 3, 4)
    _draw_segmented_table(page, (72, 180, 523, 420), 12, 2)
    doc.save(path)
    doc.close()
    return path


def test_captionless_form_detector_returns_disconnected_grid_shapes(tmp_path):
    path = _synthetic_form(tmp_path / "captionless-form.pdf")
    doc = pymupdf.open(path)
    try:
        regions = captionless_table_regions(doc[0])
    finally:
        doc.close()

    assert [(r.row_count, r.column_count) for r in regions] == [(3, 4), (12, 2)]


def test_scanner_emits_tables_and_regulatory_profile_without_find_tables(
    tmp_path, monkeypatch
):
    path = _synthetic_form(tmp_path / "regulatory-form.pdf")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("modern Tier-3 must not call page.find_tables()")

    monkeypatch.setattr(pymupdf.Page, "find_tables", forbidden, raising=False)
    manifest = PdfStructureScanner().scan(path)
    tables = [item for item in manifest.objects if item.type is ObjectType.TABLE]

    assert PDF_STRUCTURE_SCANNER_VERSION == "1.8.0"
    assert manifest.document.content_profile is ContentProfile.REGULATORY
    assert [(table.row_count, table.column_count) for table in tables] == [(3, 4), (12, 2)]
    assert all(table.planned_action == "translate_cells" for table in tables)


@pytest.mark.skipif(
    not os.environ.get("QYUNSLATION_PLAN041_SAMPLE"),
    reason="仓外 PLAN-041 实样未配置",
)
def test_plan041_real_sample_has_exact_table_gold():
    path = Path(os.environ["QYUNSLATION_PLAN041_SAMPLE"])
    manifest = PdfStructureScanner().scan(path)
    by_page: dict[int, list[tuple[int | None, int | None]]] = {}
    for table in (obj for obj in manifest.objects if obj.type is ObjectType.TABLE):
        page_no = int(table.detector_evidence[0].details["page"])
        by_page.setdefault(page_no, []).append((table.row_count, table.column_count))

    assert [len(by_page.get(page, [])) for page in range(1, 8)] == [4, 1, 2, 1, 1, 1, 4]
    assert [shape for page in range(1, 8) for shape in by_page[page]] == [
        (3, 4),
        (12, 2),
        (4, 4),
        (13, 2),
        (31, 4),
        (14, 7),
        (7, 5),
        (19, 5),
        (18, 5),
        (19, 5),
        (2, 5),
        (3, 4),
        (10, 2),
        (1, 3),
    ]
    assert manifest.extensions["truncated"] is False
    assert not [issue for issue in manifest.issues if issue.severity.value == "ERROR"]
