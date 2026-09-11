# SPDX-License-Identifier: MPL-2.0
"""PLAN-045e：文献表 source_p75 字号归一。"""
from __future__ import annotations

from qyunslation.structure.role_fitter import (
    TABLE_ROLE_SIZE,
    TABLE_SIZE_SOURCE_P75,
    FitBlock,
    fit_group,
)


def test_literature_source_p75_unifies_cells():
    blocks = [
        FitBlock("a", "table_cell", "第52周", "第52周", 10.0, False, 120, 20),
        FitBlock("b", "table_cell", "安全性随访", "安全性随访", 7.0, False, 120, 20),
    ]
    results = fit_group(blocks, table_size_mode=TABLE_SIZE_SOURCE_P75)
    assert results[0].font_size == results[1].font_size
    assert results[0].font_size >= 7.0


def test_regulatory_ladder_unchanged():
    blocks = [
        FitBlock("h", "table_header", "A", "Header", 12.0, True, 120, 20),
        FitBlock("c", "table_cell", "B", "Body", 4.2, False, 120, 16),
    ]
    results = fit_group(blocks, normalize_table_sizes=True)
    assert results[0].font_size == TABLE_ROLE_SIZE["table_header"]
    assert results[1].font_size == TABLE_ROLE_SIZE["table_cell"]
