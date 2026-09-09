"""PLAN-033i：表格局部坐标与稳定单元格块。"""
from __future__ import annotations

from pathlib import Path

import pymupdf

from qyunslation.structure.models import BlockRole
from qyunslation.structure.table_structure import (
    TABLE_OCR_MIN_DPI,
    local_frame_for,
    structure_table,
)
from qyunslation.structure.tables import TableRegion, table_regions


def _grid_pdf(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 90), "Table 1 Baseline characteristics", fontsize=11)
    # 2x2 grid
    page.draw_rect(pymupdf.Rect(72, 110, 420, 250), color=(0, 0, 0), width=0.6)
    page.draw_line(pymupdf.Point(72, 150), pymupdf.Point(420, 150), width=0.6)
    page.draw_line(pymupdf.Point(72, 200), pymupdf.Point(420, 200), width=0.6)
    page.draw_line(pymupdf.Point(246, 110), pymupdf.Point(246, 250), width=0.6)
    page.insert_text((80, 135), "Endpoint", fontsize=10)
    page.insert_text((260, 135), "Value", fontsize=10)
    page.insert_text((80, 180), "IGA 0/1", fontsize=10)
    page.insert_text((260, 180), "42%", fontsize=10)
    page.insert_text((80, 230), "* Patients with missing data were excluded.", fontsize=8)
    doc.save(path)
    doc.close()
    return path


def _rotated_pdf(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.set_rotation(90)
    page.insert_text((80, 80), "Table 1", fontsize=11)
    page.draw_rect(pymupdf.Rect(100, 100, 500, 400), color=(0, 0, 0), width=0.8)
    page.draw_line(pymupdf.Point(100, 180), pymupdf.Point(500, 180), width=0.6)
    page.draw_line(pymupdf.Point(300, 100), pymupdf.Point(300, 400), width=0.6)
    page.insert_text((120, 150), "Arm", fontsize=10)
    page.insert_text((320, 150), "N", fontsize=10)
    page.insert_text((120, 260), "Active", fontsize=10)
    page.insert_text((320, 260), "30", fontsize=10)
    doc.save(path)
    doc.close()
    return path


def _open_grid(path: Path) -> Path:
    """只有三条横线、没有完整竖网格。"""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 80), "Table 2 Response rates", fontsize=11)
    page.draw_line(pymupdf.Point(72, 100), pymupdf.Point(500, 100), width=0.8)
    page.draw_line(pymupdf.Point(72, 130), pymupdf.Point(500, 130), width=0.6)
    page.draw_line(pymupdf.Point(72, 200), pymupdf.Point(500, 200), width=0.8)
    page.insert_text((80, 120), "Group", fontsize=10)
    page.insert_text((260, 120), "Week 16", fontsize=10)
    page.insert_text((80, 160), "All", fontsize=10)
    page.insert_text((260, 160), "55%", fontsize=10)
    doc.save(path)
    doc.close()
    return path


def test_grid_table_has_stable_cell_ids(tmp_path):
    path = _grid_pdf(tmp_path / "grid.pdf")
    doc = pymupdf.open(path)
    try:
        page = doc[0]
        region = TableRegion(number=1, x0=70, y0=108, x1=422, y1=252, line_count=4)
        cells = structure_table(page, region, caption_text="Table 1 Baseline characteristics")
    finally:
        doc.close()
    ids = {cell.block_id for cell in cells}
    assert "table:1:title" in ids
    assert any(cell.role == BlockRole.TABLE_HEADER.value for cell in cells)
    assert any("IGA" in cell.text for cell in cells)
    assert any(cell.role == BlockRole.TABLE_FOOTNOTE.value for cell in cells)


def test_rotated_page_uses_local_coordinates(tmp_path):
    path = _rotated_pdf(tmp_path / "rot.pdf")
    doc = pymupdf.open(path)
    try:
        page = doc[0]
        region = TableRegion(number=1, x0=100, y0=100, x1=500, y1=400, line_count=3)
        frame = local_frame_for(page, region)
        cells = structure_table(page, region, caption_text="Table 1")
    finally:
        doc.close()
    assert frame.rotation == 90
    assert cells
    local_u = [frame.to_local((c.bbox[0] + c.bbox[2]) / 2, (c.bbox[1] + c.bbox[3]) / 2)[0] for c in cells if c.role != BlockRole.TABLE_TITLE.value]
    assert local_u
    assert min(local_u) >= -2


def test_partial_grid_still_clusters_rows_and_cols(tmp_path):
    path = _open_grid(tmp_path / "open.pdf")
    doc = pymupdf.open(path)
    try:
        page = doc[0]
        region = table_regions(page)[0]
        cells = structure_table(page, region, caption_text="Table 2 Response rates", number=2)
    finally:
        doc.close()
    texts = {cell.text for cell in cells}
    assert "Group" in texts or any("Group" in t for t in texts)
    assert any("55%" in cell.text for cell in cells)
    rows = {cell.row_index for cell in cells if cell.role != BlockRole.TABLE_TITLE.value}
    cols = {cell.column_index for cell in cells if cell.role != BlockRole.TABLE_TITLE.value}
    assert len(rows) >= 2
    assert len(cols) >= 2


def test_does_not_use_babeldoc_rapidocr_table_adapter():
    source = Path(__file__).resolve().parents[2] / "qyunslation/structure/table_structure.py"
    text = source.read_text(encoding="utf-8")
    assert "babeldoc.format.pdf.document_il.midend.table_parser" not in text
    assert "TableParser" not in text
    assert TABLE_OCR_MIN_DPI >= 300
