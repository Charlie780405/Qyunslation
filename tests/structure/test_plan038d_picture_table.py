# SPDX-License-Identifier: MPL-2.0
"""PLAN-038d：纯图片表区域回退 + OCR cell policy。"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

from qyunslation.structure.models import ObjectType, Representation, TranslationPolicy
from qyunslation.structure.scan_pdf import PdfStructureScanner
from qyunslation.structure.tables import picture_table_region, table_regions


def _png_rgb(w: int = 120, h: int = 80) -> bytes:
    # Minimal valid RGB PNG via Pillow if available, else 1x1 stub expanded by pymupdf
    try:
        from PIL import Image

        img = Image.new("RGB", (w, h), (255, 255, 255))
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc``\x00\x00"
            b"\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
        )


def _picture_table_pdf(tmp_path: Path) -> Path:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=400, height=500)
    page.insert_text((72, 72), "Table 1. Synthetic picture table", fontsize=11)
    png = _png_rgb(200, 120)
    page.insert_image(pymupdf.Rect(72, 100, 320, 260), stream=png)
    out = tmp_path / "picture-table.pdf"
    doc.save(out)
    doc.close()
    return out


def test_picture_table_region_finds_image_below_caption(tmp_path: Path):
    import pymupdf

    path = _picture_table_pdf(tmp_path)
    doc = pymupdf.open(path)
    page = doc[0]
    region = picture_table_region(page, (72, 60, 320, 80), number=1)
    doc.close()
    assert region is not None
    assert region.number == 1
    assert region.line_count == 0
    assert region.y1 > region.y0


def test_table_regions_picture_fallback(tmp_path: Path):
    import pymupdf

    path = _picture_table_pdf(tmp_path)
    doc = pymupdf.open(path)
    page = doc[0]
    regions = table_regions(page)
    doc.close()
    assert any(r.number == 1 and r.line_count == 0 for r in regions)


def test_scan_picture_table_emits_bitmap_cells(tmp_path: Path, monkeypatch):
    path = _picture_table_pdf(tmp_path)

    def fake_ocr(_data, suffix=".png"):
        # page-local boxes in region pixel space (~200x120 at 300dpi → scaled in ocr_table_region)
        # Use absolute-ish pixel boxes that map into the image
        return [
            (10, 10, 60, 30, "Drug"),
            (70, 10, 140, 30, "12.5"),
            (10, 40, 60, 60, "Dose"),
            (70, 40, 140, 60, "mg"),
        ]

    monkeypatch.setattr(
        "qyunslation.extensions.image_translate.ocr_image",
        fake_ocr,
    )
    manifest = PdfStructureScanner().scan(path)
    tables = [o for o in manifest.objects if o.type is ObjectType.TABLE]
    assert tables
    table = tables[0]
    assert table.representation is Representation.BITMAP
    assert table.row_count and table.row_count >= 2
    assert table.column_count and table.column_count >= 2
    cells = [b for b in table.translatable_blocks if b.row_index is not None]
    assert cells
    policies = {b.translation_policy for b in cells}
    assert TranslationPolicy.PRESERVE in policies or TranslationPolicy.TRANSLATE in policies
    assert any(
        ev.detector == "picture_table" for ev in (table.detector_evidence or [])
    )
