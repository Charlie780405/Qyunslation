"""PLAN-041c/041d：临床表单 token、字号、粗体与真实清除。"""
from __future__ import annotations

import hashlib

import pymupdf
import pytest

from qyunslation.structure.models import (
    BlockRole,
    BoundingBox,
    SourceStyle,
    TranslatableBlock,
)
from qyunslation.structure.role_fitter import (
    QC_FONT_BELOW_TARGET,
    FitBlock,
    fit_group,
    table_hard_fail_codes,
)
from qyunslation.structure.table_translate import TableTranslateError, translate_table_blocks
from qyunslation.structure.table_writeback import (
    output_bbox,
    paint_cell,
    redact_source_blocks,
)


def _left_hash(page) -> str:
    clip = pymupdf.Rect(0, 0, page.rect.width / 2, page.rect.height)
    return hashlib.sha256(page.get_pixmap(clip=clip, dpi=96, alpha=False).samples).hexdigest()


def test_regulatory_tokens_are_restored_exactly():
    source = (
        "登记号 CTR20243786；方案 SSGJ-611-CRS-III-01；"
        "电话 021-80297777；Email dr.luozhang@gmail.com；日期 2024-10-10"
    )
    block = TranslatableBlock(
        block_id="t:r0c0",
        source_text=source,
        role=BlockRole.TABLE_CELL,
    )

    def translator(payloads):
        protected = payloads[0]["text"]
        assert "CTR20243786" not in protected
        assert "SSGJ-611-CRS-III-01" not in protected
        assert "dr.luozhang@gmail.com" not in protected
        return {payloads[0]["id"]: f"Registration {protected}"}

    translated = translate_table_blocks([block], translator)[block.block_id]
    for token in (
        "CTR20243786",
        "SSGJ-611-CRS-III-01",
        "021-80297777",
        "dr.luozhang@gmail.com",
        "2024-10-10",
    ):
        assert token in translated


def test_dropped_regulatory_token_is_hard_failure():
    block = TranslatableBlock(
        block_id="t:r0c0",
        source_text="联系人 dr.luozhang@gmail.com",
        role=BlockRole.TABLE_CELL,
    )

    with pytest.raises(TableTranslateError, match="TABLE_TOKEN_DRIFT"):
        translate_table_blocks([block], lambda payloads: {payloads[0]["id"]: "Contact"})


def test_table_role_sizes_are_harmonized_and_floor_is_hard():
    blocks = [
        FitBlock("wide", "table_cell", "A", "短译文", 10, False, 100, 24),
        FitBlock("tight", "table_cell", "B", "无法装入窄格的较长译文", 10, False, 18, 10),
    ]
    results = fit_group(blocks)
    assert results[0].font_size == results[1].font_size
    assert QC_FONT_BELOW_TARGET in table_hard_fail_codes(results)


def test_redaction_removes_source_text_without_erasing_grid(tmp_path):
    block = TranslatableBlock(
        block_id="t:r0c0",
        source_text="源文标签",
        role=BlockRole.TABLE_HEADER,
        bbox=BoundingBox(x0=20, y0=20, x1=180, y1=55),
        source_style=SourceStyle(font_size=10, font_weight="bold"),
    )
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=100)
    page.draw_rect(pymupdf.Rect(20, 20, 180, 55), color=(0, 0, 0), width=0.8)
    page.insert_text((28, 43), block.source_text, fontname="china-ss", fontsize=10)
    before_grid_count = len(page.get_drawings())

    redact_source_blocks(page, [block], x_min_frac=None)
    paint_cell(page, block.bbox, "Translated heading", bold=True, font_size=9)
    target = tmp_path / "redacted.pdf"
    doc.save(target)
    doc.close()

    result = pymupdf.open(target)
    try:
        text = result[0].get_text()
        assert "源文标签" not in text
        assert "Translated heading" in text.replace("\xa0", " ")
        assert len(result[0].get_drawings()) >= before_grid_count
    finally:
        result.close()


def test_dual_redaction_and_paint_leave_left_half_pixel_identical():
    block = TranslatableBlock(
        block_id="t:r0c0",
        source_text="右侧源文",
        role=BlockRole.TABLE_CELL,
        bbox=BoundingBox(x0=20, y0=20, x1=180, y1=55),
        source_style=SourceStyle(font_size=10),
    )
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=100)
    page.draw_rect(pymupdf.Rect(20, 20, 180, 55), color=(0, 0, 0), width=0.8)
    page.insert_text((28, 43), "LEFT ORIGINAL", fontsize=10)
    page.draw_rect(pymupdf.Rect(220, 20, 380, 55), color=(0, 0, 0), width=0.8)
    page.insert_text((228, 43), block.source_text, fontname="china-ss", fontsize=10)
    before = _left_hash(page)

    redact_source_blocks(page, [block], x_min_frac=0.5)
    target_bbox = output_bbox(block.bbox, page.rect.width, x_min_frac=0.5)
    paint_cell(page, target_bbox, "RIGHT TARGET", bold=False, font_size=9)

    assert _left_hash(page) == before
    text = page.get_text()
    assert "LEFT ORIGINAL" in text
    assert "右侧源文" not in text
    assert "RIGHT TARGET" in text.replace("\xa0", " ")
    doc.close()
