"""PLAN-036 遗留：Tailoring 型续表题注解析。"""
from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from qyunslation.structure.captions import (
    continued_table_anchors,
    continued_table_caption_num,
    is_continued_caption,
)

TAILORING = Path("/home/dev/.hermes/attachments/Tailoring Abrocitinib Treatment.pdf")


def test_tailoring_style_continued_caption_num():
    text = "Table\u202f1\u2002 \u2009continued"
    assert is_continued_caption(text)
    assert continued_table_caption_num(text) == 1
    assert continued_table_caption_num("Table 2 Continued") == 2
    assert continued_table_caption_num("TABLE 1 | (Continued)") == 1


@pytest.mark.skipif(not TAILORING.is_file(), reason="Tailoring PDF not on host")
def test_tailoring_pdf_page7_has_table1_continued_anchor():
    doc = pymupdf.open(TAILORING)
    try:
        anchors = continued_table_anchors(doc[6])
    finally:
        doc.close()
    assert anchors
    assert anchors[0][0] == 1
