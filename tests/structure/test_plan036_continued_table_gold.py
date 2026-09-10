"""PLAN-036c：Wiley 续表 reference 金样。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from qyunslation.structure import PdfStructureScanner
from qyunslation.structure.models import ObjectType

ROOT = Path(__file__).resolve().parents[2]
CAI_PDF = ROOT / "tests/fixtures/structure/reference/cai-2025-table1-continued.pdf"
TRUTH = ROOT / "tests/fixtures/structure/cai-2025-table1-continued.truth.json"


@pytest.fixture(scope="module")
def truth():
    return json.loads(TRUTH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def cai_manifest():
    assert CAI_PDF.is_file(), "CONTINUED_TABLE_GOLD_MISSING"
    return PdfStructureScanner().scan(CAI_PDF)


def test_reference_pdf_matches_truth_sha256(truth):
    digest = hashlib.sha256(CAI_PDF.read_bytes()).hexdigest()
    assert digest == truth["source"]["sha256"]


def test_wiley_table1_has_multiple_occurrences_one_semantic_count(cai_manifest, truth):
    tables = [o for o in cai_manifest.objects if o.type is ObjectType.TABLE]
    table1 = [t for t in tables if t.semantic_id == "table:1"]
    assert cai_manifest.summary.table_count == truth["continued_table"]["summary_table_count"]
    assert len(table1) >= truth["continued_table"]["min_occurrences"]
    indices = sorted(t.semantic_occurrence_index for t in table1)
    assert indices == list(range(1, len(indices) + 1))


def test_first_occurrence_has_translatable_blocks(cai_manifest):
    first = min(
        (o for o in cai_manifest.objects if o.type is ObjectType.TABLE and o.semantic_id == "table:1"),
        key=lambda o: o.semantic_occurrence_index,
    )
    assert first.translatable_blocks
