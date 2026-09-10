"""PLAN-030-table：PDF Table 单元格网格与 row/column 计数。"""
from __future__ import annotations

from pathlib import Path

import pytest

from qyunslation.structure import PdfStructureScanner
from qyunslation.structure.models import ObjectType

ROOT = Path(__file__).resolve().parents[2]
LJAE = ROOT / "tests/fixtures/structure/reference/ljae439.pdf"
NATURE = ROOT / "tests/fixtures/structure/reference/nature_comm_53384.pdf"


@pytest.fixture(scope="module")
def ljae_manifest():
    return PdfStructureScanner().scan(LJAE)


@pytest.fixture(scope="module")
def nature_manifest():
    return PdfStructureScanner().scan(NATURE)


@pytest.mark.parametrize("fixture_name", ["ljae_manifest", "nature_manifest"])
def test_every_table_has_grid_dimensions(fixture_name, request):
    manifest = request.getfixturevalue(fixture_name)
    tables = [o for o in manifest.objects if o.type is ObjectType.TABLE]
    assert tables
    for table in tables:
        assert table.row_count is not None and table.row_count >= 2, table.semantic_id
        assert table.column_count is not None and table.column_count >= 2, table.semantic_id
        assert table.planned_action == "translate_cells"
        assert table.translatable_blocks


def test_ljae_table_1_is_multi_column(ljae_manifest):
    table1 = next(
        o for o in ljae_manifest.objects if o.semantic_id == "table:1"
    )
    assert table1.column_count >= 3


def test_nature_tables_match_expected_counts(nature_manifest):
    tables = {
        o.semantic_id: o
        for o in nature_manifest.objects
        if o.type is ObjectType.TABLE
    }
    assert set(tables) == {"table:1", "table:2", "table:3"}
    for table in tables.values():
        assert table.row_count >= 2
        assert table.column_count >= 2
