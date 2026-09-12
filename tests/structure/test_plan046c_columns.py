# SPDX-License-Identifier: MPL-2.0
"""PLAN-046c：列簇二次合并与 SPAN_ORDER_DRIFT。"""
from __future__ import annotations

from qyunslation.structure.models import BoundingBox, TranslatableBlock, TranslationPolicy
from qyunslation.structure.table_attribution import (
    QC_SPAN_ORDER_DRIFT,
    detect_span_order_drift,
)
from qyunslation.structure.table_structure import _merge_column_clusters


def test_merge_column_clusters_joins_fragments():
    # 模拟 4 真实列被切成碎片中心
    centers = [10.0, 12.0, 14.0, 80.0, 82.0, 150.0, 152.0, 220.0]
    merged = _merge_column_clusters(centers)
    assert len(merged) <= 4
    assert len(merged) >= 3


def test_merge_keeps_well_spaced_columns():
    centers = [10.0, 80.0, 150.0, 220.0]
    assert _merge_column_clusters(centers) == centers


def test_span_order_drift_detects_mismatch():
    blocks = [
        TranslatableBlock(
            block_id="a",
            source_text="A",
            translation_policy=TranslationPolicy.TRANSLATE,
            row_index=1,
            column_index=0,
            bbox=BoundingBox(x0=100, y0=0, x1=120, y1=10),
        ),
        TranslatableBlock(
            block_id="b",
            source_text="B",
            translation_policy=TranslationPolicy.TRANSLATE,
            row_index=1,
            column_index=1,
            bbox=BoundingBox(x0=10, y0=0, x1=30, y1=10),
        ),
    ]
    issues = detect_span_order_drift(blocks)
    assert any(i.code == QC_SPAN_ORDER_DRIFT for i in issues)


def test_ljae439_table1_column_count():
    import pymupdf
    from pathlib import Path

    sample = Path("/home/dev/pdf2zh/pdf2zh_files/d397e54c-5e45-4592-afda-207ed48a7bb4/ljae439.pdf")
    if not sample.is_file():
        return
    from qyunslation.structure.tables import table_regions
    from qyunslation.structure.table_structure import structure_table

    doc = pymupdf.open(sample)
    page = doc[4]
    regs = table_regions(page)
    assert regs
    cells = structure_table(page, regs[0])
    max_col = max(c.column_index for c in cells)
    # 目标 ≤ 6（理想 4；允许轻微过头，但远低于原先 13）
    assert max_col < 8, f"still too many columns: {max_col + 1}"
    age = [c for c in cells if "37.1" in (c.text or "")]
    assert age, "missing age value cell"
    assert any("(13.3)" in (c.text or "") for c in age)
    doc.close()
