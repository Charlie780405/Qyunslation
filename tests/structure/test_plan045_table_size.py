# SPDX-License-Identifier: MPL-2.0
"""PLAN-045e：文献表 source_p75 字号归一。"""
from __future__ import annotations

from qyunslation.structure.models import (
    BoundingBox,
    SourceStyle,
    TranslatableBlock,
    TranslationPolicy,
)
from qyunslation.structure.role_fitter import (
    QC_ROLE_SIZE_DRIFT,
    TABLE_ROLE_SIZE,
    TABLE_SIZE_SOURCE_P75,
    FitBlock,
    fit_group,
)
from qyunslation.structure.table_qc import QC_SOURCE_RESIDUE, evaluate_table_qc


def test_literature_source_p75_unifies_cells():
    blocks = [
        FitBlock("a", "table_cell", "第52周", "第52周", 10.0, False, 120, 20),
        FitBlock("b", "table_cell", "安全性随访", "安全性随访", 7.0, False, 120, 20),
    ]
    results = fit_group(blocks, table_size_mode=TABLE_SIZE_SOURCE_P75)
    assert results[0].font_size == results[1].font_size
    assert results[0].font_size >= 7.0


def test_english_target_chinese_is_not_residue():
    block = TranslatableBlock(
        block_id="c0",
        source_text="Week 52",
        translation_policy=TranslationPolicy.TRANSLATE,
        role="table_cell",
        source_style=SourceStyle(font_size=10),
        bbox=BoundingBox(x0=0, y0=0, x1=80, y1=16),
        row_index=0,
        column_index=0,
    )
    records, hard = evaluate_table_qc([block], {"c0": "第52周"})
    assert QC_SOURCE_RESIDUE not in records[0].qc
    assert not any(str(c).startswith("RESIDUE_RATE") for c in hard)


def test_source_p75_overflow_does_not_flag_drift():
    blocks = [
        FitBlock("a", "table_cell", "Week 52", "第52周", 10.0, False, 120, 20),
        FitBlock(
            "b",
            "table_cell",
            "long",
            "一段很长很长很长很长很长的中文译文塞不进窄格",
            10.0,
            False,
            22,
            12,
        ),
    ]
    results = fit_group(blocks, table_size_mode=TABLE_SIZE_SOURCE_P75)
    assert results[1].overflow
    assert QC_ROLE_SIZE_DRIFT not in results[0].qc
    assert QC_ROLE_SIZE_DRIFT not in results[1].qc


def test_regulatory_ladder_unchanged():
    blocks = [
        FitBlock("h", "table_header", "A", "Header", 12.0, True, 120, 20),
        FitBlock("c", "table_cell", "B", "Body", 4.2, False, 120, 16),
    ]
    results = fit_group(blocks, normalize_table_sizes=True)
    assert results[0].font_size == TABLE_ROLE_SIZE["table_header"]
    assert results[1].font_size == TABLE_ROLE_SIZE["table_cell"]
