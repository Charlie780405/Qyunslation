# SPDX-License-Identifier: MPL-2.0
"""PLAN-080：Word / PPT 正文段落的保留（默认关闭，开启后与 PDF 同一套规则）。"""
from __future__ import annotations

import pytest

from qyunslation.structure import office_preserve as op
from qyunslation.structure.docx_table_exec import partition_docx_segments
from qyunslation.structure.pptx_table_exec import partition_pptx_segments

CITATION = (
    "1. Smith J, Doe A, Lee K. Efficacy of drug X in atopic dermatitis. J Allergy Clin Immunol. "
    "2024;153(2):345-52. doi:10.1016/j.jaci.2023.10.001"
)
BODY = "The protocol synopsis does not detail planned subgroup analyses for the primary efficacy endpoint."
NUMBERED_BODY = "2. " + BODY

ORIGINALS = [
    "Alex Morgan, MD",
    "Medical Director",
    BODY,
    NUMBERED_BODY,
    "References",
    CITATION,
    "2. Wollenberg A, et al. Consensus-based European guidelines. J Eur Acad Dermatol 2018;32:657-82.",
]


def docx_elements(n: int) -> list[dict]:
    return [{"table_path": None} for _ in range(n)]


def pptx_elements(n: int) -> list[dict]:
    return [{"table_cell_ref": None} for _ in range(n)]


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv(op.MODE_ENV, raising=False)


@pytest.mark.parametrize("partition,elements", [(partition_docx_segments, docx_elements), (partition_pptx_segments, pptx_elements)])
def test_default_off_sends_every_paragraph_to_translation(partition, elements):
    batch = partition(ORIGINALS, elements(len(ORIGINALS)), None)
    assert batch.llm_texts == ORIGINALS
    assert batch.preserved_indices == frozenset()


@pytest.mark.parametrize("partition,elements", [(partition_docx_segments, docx_elements), (partition_pptx_segments, pptx_elements)])
def test_on_keeps_names_titles_and_references_but_translates_body_and_numbered_questions(monkeypatch, partition, elements):
    monkeypatch.setenv(op.MODE_ENV, "on")
    batch = partition(ORIGINALS, elements(len(ORIGINALS)), None)
    assert batch.preserved_indices == frozenset({0, 1, 4, 5, 6})
    assert batch.llm_texts == [BODY, NUMBERED_BODY]


def test_table_cells_keep_names_and_titles_but_not_the_reference_state_machine(monkeypatch):
    monkeypatch.setenv(op.MODE_ENV, "on")
    originals = ["Medical Director", "Efficacy was good", "300 mg", "References", "A follow-up cell"]
    elements = [{"table_path": (0, 0, i)} for i in range(5)]
    batch = partition_docx_segments(originals, elements, None)
    assert 0 in batch.preserved_indices                     # 职务：新规则保留
    assert 1 not in batch.preserved_indices                 # 普通文字：照常翻译
    assert 2 in batch.preserved_indices                     # 剂量：原有的单元格策略保留
    assert 4 not in batch.preserved_indices                 # "References" 单元格不会让后面的单元格都被保留
    monkeypatch.delenv(op.MODE_ENV)
    off = partition_docx_segments(originals, elements, None)
    assert 0 not in off.preserved_indices                   # 关闭时与以前完全一致


def test_each_document_has_its_own_references_state(monkeypatch):
    """第一份文档以参考文献区结尾，不能影响第二份文档开头的正文。"""
    monkeypatch.setenv(op.MODE_ENV, "on")
    first = ["References", "some entry that follows the heading"]
    second = [BODY, NUMBERED_BODY]
    a = partition_docx_segments(first, docx_elements(2), None)
    b = partition_docx_segments(second, docx_elements(2), None)
    assert a.preserved_indices == frozenset({0, 1})
    assert b.preserved_indices == frozenset()


def test_gate_flag_parsing(monkeypatch):
    for value, expected in (("on", True), ("1", True), ("TRUE", True), ("off", False), ("", False), ("maybe", False)):
        monkeypatch.setenv(op.MODE_ENV, value)
        assert op.office_preserve_enabled() is expected
    monkeypatch.delenv(op.MODE_ENV, raising=False)
    assert op.new_office_gate() is None


def test_real_docx_attendee_table_and_reference_section(monkeypatch, tmp_path):
    """走真实的 walk_docx：参会人表格里的人名与职务、参考文献区被保留，正文与编号问题照常翻译。"""
    docx = pytest.importorskip("docx")
    from qyunslation.structure.docx_walk import walk_docx

    document = docx.Document()
    document.add_paragraph("Background")
    document.add_paragraph(BODY)
    document.add_paragraph(NUMBERED_BODY)
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Alex Morgan, MD"
    table.cell(0, 1).text = "Deputy Director"
    table.cell(1, 0).text = "Statistical Issues"
    table.cell(1, 1).text = "Medical Director"
    document.add_paragraph("References")
    document.add_paragraph(CITATION)
    path = tmp_path / "doc.docx"
    document.save(path)

    _doc, _segments, elements, texts = walk_docx(path.read_bytes())
    monkeypatch.setenv(op.MODE_ENV, "on")
    batch = partition_docx_segments(texts, elements, None)
    sent = [texts[i] for i in batch.llm_to_original]
    kept = [texts[i] for i in sorted(batch.preserved_indices)]
    assert "Background" in sent and BODY in sent and NUMBERED_BODY in sent and "Statistical Issues" in sent
    for expected in ("Alex Morgan, MD", "Deputy Director", "Medical Director", "References", CITATION):
        assert expected in kept, expected
