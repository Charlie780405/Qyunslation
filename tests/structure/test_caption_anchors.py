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
    table_caption_num,
)


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


def test_nature_page10_has_figure_5_anchor():
    doc = pymupdf.open(NATURE)
    try:
        anchors = caption_anchors(doc[9])
    finally:
        doc.close()
    assert ("figure", 5) in {(k, n) for k, n, _y, _b in anchors}
