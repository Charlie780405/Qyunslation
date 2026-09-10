"""PLAN-041d：完整性与版式硬门禁。"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from qyunslation.structure.models import (
    BlockRole,
    BoundingBox,
    ObjectType,
    Representation,
    SourceStyle,
    TableObject,
    TranslatableBlock,
    TranslationPolicy,
)
from qyunslation.structure.role_fitter import (
    QC_FONT_BELOW_TARGET,
    QC_OVERFLOW,
    FitBlock,
    FitResult,
    fit_group,
    hard_fail_codes,
    table_hard_fail_codes,
    wrap_lines,
)
from qyunslation.structure.scan_pdf import PdfStructureScanner
from qyunslation.structure.table_qc import (
    QC_MISSING_TARGET,
    QC_SOURCE_RESIDUE,
    evaluate_table_qc,
    source_qc_ledger,
    source_residue_on_page,
)
from qyunslation.structure.table_translate import translate_table_blocks
from qyunslation.structure.table_writeback import paint_cell, redact_source_blocks


def test_empty_preserve_cell_is_not_missing_target():
    block = TranslatableBlock(
        block_id="t:r1c1",
        source_text="",
        role=BlockRole.TABLE_CELL,
        translation_policy=TranslationPolicy.PRESERVE,
    )
    out = translate_table_blocks(
        [block],
        lambda payloads: (_ for _ in ()).throw(AssertionError("empty PRESERVE must not call LLM")),
    )
    assert out[block.block_id] == ""


def test_translate_cjk_residue_and_missing_target_are_hard():
    leftover = TranslatableBlock(
        block_id="t:zh",
        source_text="主要终点",
        role=BlockRole.TABLE_CELL,
        translation_policy=TranslationPolicy.TRANSLATE,
        source_style=SourceStyle(font_size=10),
        bbox=BoundingBox(x0=10, y0=10, x1=120, y1=28),
        row_index=0,
        column_index=0,
    )
    missing = TranslatableBlock(
        block_id="t:miss",
        source_text="次要终点",
        role=BlockRole.TABLE_CELL,
        translation_policy=TranslationPolicy.TRANSLATE,
        source_style=SourceStyle(font_size=10),
        bbox=BoundingBox(x0=10, y0=30, x1=120, y1=48),
        row_index=1,
        column_index=0,
    )
    results = [
        FitResult(text="主要终点", font_size=10, bold=False, dpi=300),
        FitResult(text="", font_size=10, bold=False, dpi=300, qc=["UNTRANSLATED"]),
    ]
    _records, hard = evaluate_table_qc(
        [leftover, missing],
        {"t:zh": "主要终点", "t:miss": ""},
        results,
    )
    assert QC_SOURCE_RESIDUE in hard
    assert QC_MISSING_TARGET in hard


def test_font_below_is_table_hard_not_image_hard():
    results = fit_group(
        [
            FitBlock("wide", "table_cell", "A", "short", 10, False, 100, 24),
            FitBlock("tight", "table_cell", "B", "cannot fit this long English phrase", 10, False, 18, 10),
        ]
    )
    assert QC_FONT_BELOW_TARGET in table_hard_fail_codes(results)
    assert QC_FONT_BELOW_TARGET not in hard_fail_codes(results)


def test_overflow_without_continuation_is_hard_with_continuation_is_not():
    block = TranslatableBlock(
        block_id="t:r0c0",
        source_text="label",
        role=BlockRole.TABLE_CELL,
        bbox=BoundingBox(x0=10, y0=10, x1=22, y1=16),
        source_style=SourceStyle(font_size=9),
        row_index=0,
        column_index=0,
    )
    result = FitResult(
        text="this English sentence cannot fit",
        font_size=9,
        bold=False,
        dpi=300,
        overflow=True,
        qc=[QC_OVERFLOW],
    )
    _r1, hard = evaluate_table_qc([block], {"t:r0c0": result.text}, [result])
    assert QC_OVERFLOW in hard
    _r2, hard2 = evaluate_table_qc(
        [block], {"t:r0c0": result.text}, [result], leftover=[[result.text]]
    )
    assert QC_OVERFLOW not in hard2


def test_wrap_lines_actually_wraps_english_words():
    assert len(wrap_lines("primary endpoint after induction week 16", 12)) >= 2


def test_redaction_source_residue_detected(tmp_path):
    block = TranslatableBlock(
        block_id="t:r0c0",
        source_text="源文标签",
        role=BlockRole.TABLE_CELL,
        bbox=BoundingBox(x0=20, y0=20, x1=180, y1=55),
        source_style=SourceStyle(font_size=10),
        translation_policy=TranslationPolicy.TRANSLATE,
    )
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=80)
    page.insert_text((28, 43), block.source_text, fontname="china-ss", fontsize=10)
    assert source_residue_on_page(page, [block], {"t:r0c0": "Translated heading"}, x_min_frac=None)
    redact_source_blocks(page, [block], x_min_frac=None)
    paint_cell(page, block.bbox, "Translated heading", bold=False, font_size=9)
    assert not source_residue_on_page(page, [block], {"t:r0c0": "Translated heading"}, x_min_frac=None)
    dest = tmp_path / "qc.pdf"
    doc.save(dest)
    doc.close()


def _cell_pdf(path: Path, *, bbox: tuple[float, float, float, float], text: str) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=160)
    page.draw_rect(pymupdf.Rect(*bbox), color=(0, 0, 0), width=0.6)
    page.insert_text((bbox[0] + 4, bbox[1] + 16), text, fontname="china-ss", fontsize=9)
    doc.save(path)
    doc.close()
    return path


def _table_manifest(block: TranslatableBlock) -> SimpleNamespace:
    table = TableObject.model_construct(
        type=ObjectType.TABLE,
        object_id="obj:" + "a" * 64,
        canvas_id="page:1",
        representation=Representation.VECTOR,
        semantic_id="table:1",
        translatable_blocks=[block],
        row_count=1,
        column_count=1,
    )
    return SimpleNamespace(
        objects=[table],
        extensions={},
        issues=[],
        document=SimpleNamespace(source_sha256="0" * 64),
        refresh_summary=lambda: None,
    )


def test_hard_fail_refuses_partial_product(tmp_path):
    from pdf_table_translate import translate_pdf_tables

    bbox = (20, 30, 70, 52)
    src = _cell_pdf(tmp_path / "src.pdf", bbox=bbox, text="主要终点")
    block = TranslatableBlock(
        block_id="t:r0c0",
        source_text="主要终点",
        role=BlockRole.TABLE_CELL,
        translation_policy=TranslationPolicy.TRANSLATE,
        bbox=BoundingBox(x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3]),
        source_style=SourceStyle(font_size=10),
        row_index=0,
        column_index=0,
    )
    dest = translate_pdf_tables(
        src,
        structure_manifest=_table_manifest(block),
        translator=lambda payloads: {
            item["id"]: "This translated phrase is far too long for a tiny regulatory cell"
            for item in payloads
        },
    )
    assert dest == src
    assert not src.with_name(src.stem + ".tbltr.pdf").is_file()


def test_clean_writeback_emits_cell_ledger(tmp_path):
    from pdf_table_translate import translate_pdf_tables

    bbox = (20, 30, 360, 80)
    src = _cell_pdf(tmp_path / "ok.pdf", bbox=bbox, text="主要终点")
    block = TranslatableBlock(
        block_id="t:r0c0",
        source_text="主要终点",
        role=BlockRole.TABLE_CELL,
        translation_policy=TranslationPolicy.TRANSLATE,
        bbox=BoundingBox(x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3]),
        source_style=SourceStyle(font_size=10),
        row_index=0,
        column_index=0,
    )
    dest = translate_pdf_tables(
        src,
        structure_manifest=_table_manifest(block),
        translator=lambda payloads: {item["id"]: "Primary endpoint" for item in payloads},
    )
    assert dest != src and dest.is_file()
    text = pymupdf.open(dest)[0].get_text()
    assert "主要终点" not in text
    assert "Primary endpoint" in text.replace("\xa0", " ")


@pytest.mark.skipif(
    not os.environ.get("QYUNSLATION_PLAN041_SAMPLE"),
    reason="仓外 PLAN-041 实样未配置",
)
def test_plan041_real_sample_source_ledger_without_llm():
    path = Path(os.environ["QYUNSLATION_PLAN041_SAMPLE"])
    manifest = PdfStructureScanner().scan(path)
    rows = source_qc_ledger(manifest)
    tables = {row["table"] for row in rows}
    assert len(tables) == 14
    assert all("policy" in row and "protected_tokens" in row for row in rows)
    empties = [row for row in rows if row["empty_source"]]
    assert all(row["policy"] == "PRESERVE" for row in empties)
    assert all(row["row"] is not None and row["column"] is not None for row in rows)
