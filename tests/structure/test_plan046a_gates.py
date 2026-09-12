# SPDX-License-Identifier: MPL-2.0
"""PLAN-046a：文献表门禁复原 + COLUMN_CLUSTER_DRIFT。"""
from __future__ import annotations

from qyunslation.structure.models import (
    BoundingBox,
    SourceStyle,
    TranslatableBlock,
    TranslationPolicy,
)
from qyunslation.structure.table_qc import (
    QC_COLUMN_CLUSTER_DRIFT,
    TABLE_QC_SOFT,
    TABLE_QC_SOFT_REGULATORY,
    detect_column_cluster_drift,
)


def _block(bid: str, text: str, *, row: int, col: int) -> TranslatableBlock:
    return TranslatableBlock(
        block_id=bid,
        source_text=text,
        translation_policy=TranslationPolicy.TRANSLATE,
        role="table_cell",
        source_style=SourceStyle(font_size=8),
        bbox=BoundingBox(x0=0, y0=0, x1=40, y1=12),
        row_index=row,
        column_index=col,
    )


def test_column_cluster_drift_requires_fragments_and_sparse():
    """PLAN-047e：须碎片≥2 且列稀疏同时命中。"""
    # 仅碎片、列不稀疏 → 不触发
    fragments_only = [
        _block("a", "Age (years)", row=1, col=0),
        _block("b", "( N", row=0, col=1),
        _block("c", "=", row=0, col=2),
        _block("d", "130)", row=0, col=3),
        _block("e", "37.1 (13.3)", row=1, col=1),
    ]
    assert detect_column_cluster_drift(fragments_only) is None

    # 仅稀疏、无碎片 → 不触发
    sparse_only = [
        _block("r1c0", "Age", row=1, col=0),
        _block("r1c4", "37.1 (13.3)", row=1, col=4),
        _block("r1c8", "38.9 (16.3)", row=1, col=8),
        _block("r1c12", "38.3 (13.2)", row=1, col=12),
        _block("r2c0", "Male", row=2, col=0),
        _block("r2c4", "74 (56.9)", row=2, col=4),
        _block("r2c8", "68 (50.7)", row=2, col=8),
        _block("r2c12", "41 (56)", row=2, col=12),
    ]
    assert detect_column_cluster_drift(sparse_only) is None

    # 二者同时 → 触发
    both = [
        _block("b", "( N", row=0, col=1),
        _block("c", "=", row=0, col=2),
        _block("r1c0", "Age", row=1, col=0),
        _block("r1c4", "37.1 (13.3)", row=1, col=4),
        _block("r1c8", "38.9 (16.3)", row=1, col=8),
        _block("r1c12", "38.3 (13.2)", row=1, col=12),
        _block("r2c0", "Male", row=2, col=0),
        _block("r2c4", "74 (56.9)", row=2, col=4),
        _block("r2c8", "68 (50.7)", row=2, col=8),
        _block("r2c12", "41 (56)", row=2, col=12),
    ]
    assert detect_column_cluster_drift(both) == QC_COLUMN_CLUSTER_DRIFT


def test_column_cluster_drift_on_fragments():
    # 保留旧名：现改为需同时稀疏；构造同时命中的样例
    blocks = [
        _block("a", "Age (years)", row=1, col=0),
        _block("b", "( N", row=0, col=1),
        _block("c", "=", row=0, col=5),
        _block("d", "130)", row=0, col=9),
        _block("e", "37.1 (13.3)", row=1, col=12),
        _block("f", "Male", row=2, col=0),
        _block("g", "74", row=2, col=4),
        _block("h", "68", row=2, col=8),
        _block("i", "41", row=2, col=12),
    ]
    assert detect_column_cluster_drift(blocks) == QC_COLUMN_CLUSTER_DRIFT


def test_column_cluster_drift_on_sparse_columns():
    # 稀疏 + 碎片
    blocks = [
        _block("frag1", "( N", row=0, col=1),
        _block("frag2", "=", row=0, col=2),
        _block("r1c0", "Age", row=1, col=0),
        _block("r1c4", "37.1 (13.3)", row=1, col=4),
        _block("r1c8", "38.9 (16.3)", row=1, col=8),
        _block("r1c12", "38.3 (13.2)", row=1, col=12),
        _block("r2c0", "Male", row=2, col=0),
        _block("r2c4", "74 (56.9)", row=2, col=4),
        _block("r2c8", "68 (50.7)", row=2, col=8),
        _block("r2c12", "41 (56)", row=2, col=12),
    ]
    assert detect_column_cluster_drift(blocks) == QC_COLUMN_CLUSTER_DRIFT


def test_healthy_four_column_table_no_drift():
    blocks = [
        _block("h0", "Characteristic", row=0, col=0),
        _block("h1", "Q2W", row=0, col=1),
        _block("h2", "Q4W", row=0, col=2),
        _block("h3", "Placebo", row=0, col=3),
        _block("r1c0", "Age (years), mean (SD)", row=1, col=0),
        _block("r1c1", "37.1 (13.3)", row=1, col=1),
        _block("r1c2", "38.9 (16.3)", row=1, col=2),
        _block("r1c3", "38.3 (13.2)", row=1, col=3),
    ]
    assert detect_column_cluster_drift(blocks) is None


def test_literature_isolate_order_in_script():
    """literature 优先于 isolate_residue，source_p75 可达。"""
    from pathlib import Path

    src = Path("scripts/pdf_table_translate.py").read_text(encoding="utf-8")
    assert 'table_size_mode = "source_p75"' in src
    lit_pos = src.index("if literature:")
    iso_pos = src.index("elif isolate_residue:")
    assert lit_pos < iso_pos
    # literature 不再并入 isolate_residue
    assert "or literature" not in src.split("isolate_residue =")[1].split("if literature")[0]


def test_column_cluster_drift_not_soft():
    assert QC_COLUMN_CLUSTER_DRIFT not in TABLE_QC_SOFT
    assert QC_COLUMN_CLUSTER_DRIFT not in TABLE_QC_SOFT_REGULATORY
