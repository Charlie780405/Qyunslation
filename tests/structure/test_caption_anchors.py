from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pymupdf
import pytest

from qyunslation.structure.captions import (
    caption_anchors,
    figure_caption_num,
    is_continued_caption,
    is_toc_line,
    join_span_texts,
    table_caption_num,
)
from qyunslation.structure.scan_pdf import (
    PDF_STRUCTURE_SCANNER_VERSION,
    PdfStructureScanner,
)
from tests.structure.sample_paths import PLAN033_SAMPLE_SHA256, plan033_academic_sample


ROOT = Path(__file__).resolve().parents[2]
LJAE = ROOT / "tests/fixtures/structure/reference/ljae439.pdf"
NATURE = ROOT / "tests/fixtures/structure/reference/nature_comm_53384.pdf"
NATURE_TRUTH = ROOT / "tests/fixtures/structure/nature_comm_53384.truth.json"


def test_table_and_figure_number_parsing():
    assert table_caption_num("Table 3 | Efficacy outcomes") == 3
    assert table_caption_num("Table\u20021 Title") == 1
    assert table_caption_num("TABLE II. Safety") == 2
    assert figure_caption_num("Figure 5. Kaplan–Meier") == 5
    assert figure_caption_num("Fig. 2 Study design") == 2
    assert table_caption_num("as shown in Table 2") is None
    assert figure_caption_num("see Figure 1") is None


def test_toc_and_continued_captions_are_rejected():
    assert is_toc_line("Table 1 ........ 12")
    assert is_continued_caption("Table 2 Continued")
    assert is_continued_caption("(continues)")
    assert not is_continued_caption("Table 2 Safety outcomes")


def test_nature_fixture_hash_matches_truth():
    truth = json.loads(NATURE_TRUTH.read_text(encoding="utf-8"))
    assert truth["usage_scope"] == "TEST_FIXTURE_ONLY"
    assert hashlib.sha256(NATURE.read_bytes()).hexdigest() == truth["source"]["sha256"]


def test_ljae439_page5_has_table_2_anchor():
    doc = pymupdf.open(LJAE)
    try:
        anchors = caption_anchors(doc[4])
    finally:
        doc.close()
    assert ("table", 2) in {(k, n) for k, n, _y, _b in anchors}


def test_join_span_texts_restores_word_boundary():
    assert join_span_texts(["Table 2", "Response to Dupilumab"]) == (
        "Table 2 Response to Dupilumab"
    )
    assert join_span_texts(["Fig.", " 2"]) == "Fig. 2"
    assert join_span_texts(["1", ",", "234"]) == "1,234"
    assert join_span_texts(["Table 2.", "Response"]) == "Table 2. Response"
    assert table_caption_num("Table 2Response to Dupilumab") is None


def test_caption_span_gap_fixture_recovers_tables_2_to_4(generated_structure_fixtures):
    doc = pymupdf.open(generated_structure_fixtures / "caption-span-gap.pdf")
    try:
        page = doc[0]
        raw = "".join(
            span.get("text", "")
            for block in page.get_text("dict")["blocks"]
            if block.get("type") == 0
            for line in block.get("lines", [])
            for span in line.get("spans", [])
        )
        assert "Table 2Response" in raw
        anchors = {(kind, num) for kind, num, _y, _b in caption_anchors(page)}
    finally:
        doc.close()
    assert ("figure", 1) in anchors
    assert {("table", 2), ("table", 3), ("table", 4)} <= anchors
    assert sum(1 for kind, num in anchors if kind == "table" and num == 4) == 1


def test_scanner_version_bumped_for_caption_join():
    assert PDF_STRUCTURE_SCANNER_VERSION == "1.4.0"


def test_plan033_sample_counts_two_figures_and_four_tables():
    path = plan033_academic_sample()
    if path is None:
        pytest.skip("PLAN-033 11-page academic PDF is not on this host")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != PLAN033_SAMPLE_SHA256:
        pytest.skip(f"PLAN-033 sample hash drifted: {digest}")
    manifest = PdfStructureScanner().scan(path)
    assert manifest.summary.figure_count == 2
    assert manifest.summary.table_count == 4
    assert {item.semantic_id for item in manifest.objects if item.type.value == "FIGURE"} == {
        "figure:1",
        "figure:2",
    }
    assert {item.semantic_id for item in manifest.objects if item.type.value == "TABLE"} == {
        "table:1",
        "table:2",
        "table:3",
        "table:4",
    }


def test_nature_page10_has_figure_5_anchor():
    doc = pymupdf.open(NATURE)
    try:
        anchors = caption_anchors(doc[9])
    finally:
        doc.close()
    assert ("figure", 5) in {(k, n) for k, n, _y, _b in anchors}
