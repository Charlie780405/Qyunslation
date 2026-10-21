"""PLAN-085：横向整页转正再翻译、单格重译、静态中文字体、符号字形 QA。"""
from __future__ import annotations

from pathlib import Path

import pymupdf

from qyunslation.pipeline.qa.pdf_inspect import check_translation_text
from qyunslation.structure import cjk_font, pdf_rotate
from qyunslation.structure.models import (
    BoundingBox,
    TranslatableBlock,
    TranslationPolicy,
)
from qyunslation.structure.table_translate import translate_table_blocks
from qyunslation.structure.text_sanitize import symbol_glyph_evidence


def _rotated_pdf(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    for i in range(6):
        page.insert_text(
            (100 + i * 20, 700),
            f"Rotated table row {i} with enough characters for detection and more more more",
            fontsize=10,
            rotate=90,
        )
    page.insert_text((50, 780), "footer line", fontsize=8)
    doc.save(str(path))
    return path


def _dirs(page) -> set[tuple[int, int]]:
    return {
        (round(line["dir"][0]), round(line["dir"][1]))
        for block in page.get_text("dict")["blocks"]
        for line in block.get("lines", [])
    }


def test_rotated_page_is_normalized_then_restored(tmp_path):
    src = _rotated_pdf(tmp_path / "in.pdf")
    norm = tmp_path / "norm.pdf"
    records = pdf_rotate.normalize_rotated_pages(src, norm)
    assert [(r.page, r.cw) for r in records] == [(0, 90)]
    page = pymupdf.open(str(norm))[0]
    assert (page.rect.width, page.rect.height) == (792, 612)
    assert (1, 0) in _dirs(page)

    out = tmp_path / "out.pdf"
    out.write_bytes(norm.read_bytes())
    assert pdf_rotate.finish_rotated_pages(out, src, records, dual=False)["restored"] == 1
    back = pymupdf.open(str(out))[0]
    assert (back.rect.width, back.rect.height) == (612, 792)
    assert (0, -1) in _dirs(back)
    assert "footer line" in back.get_text()  # 页脚被盖回原样


def test_dual_spread_is_restored_with_original_left_half(tmp_path):
    src = _rotated_pdf(tmp_path / "in.pdf")
    norm = tmp_path / "norm.pdf"
    records = pdf_rotate.normalize_rotated_pages(src, norm)
    normalized = pymupdf.open(str(norm))
    dual = pymupdf.open()
    spread = dual.new_page(width=792 * 2, height=612)
    spread.show_pdf_page(pymupdf.Rect(0, 0, 792, 612), normalized, 0)
    spread.show_pdf_page(pymupdf.Rect(792, 0, 1584, 612), normalized, 0)
    out = tmp_path / "dual.pdf"
    dual.save(str(out))
    assert pdf_rotate.finish_rotated_pages(out, src, records, dual=True)["restored"] == 1
    page = pymupdf.open(str(out))[0]
    assert (page.rect.width, page.rect.height) == (1224, 792)


def test_upright_documents_are_left_alone(tmp_path):
    doc = pymupdf.open()
    doc.new_page(width=612, height=792).insert_text((72, 72), "plain " * 80, fontsize=10)
    src = tmp_path / "plain.pdf"
    doc.save(str(src))
    target = tmp_path / "norm.pdf"
    assert pdf_rotate.normalize_rotated_pages(src, target) == []
    assert not target.exists()


def test_rotation_switch_off(tmp_path, monkeypatch):
    monkeypatch.setenv("QYUNSLATION_ROTATED_PAGES", "0")
    src = _rotated_pdf(tmp_path / "in.pdf")
    assert pdf_rotate.normalize_rotated_pages(src, tmp_path / "n.pdf") == []


def test_variable_font_is_replaced_by_static(tmp_path, monkeypatch):
    thin = tmp_path / "Thin.ttf"
    thin.write_bytes(b"x")
    static = tmp_path / "NotoSansSC-Regular.otf"
    static.write_bytes(b"x")
    monkeypatch.setattr(cjk_font, "_FONT_HOME", tmp_path)
    monkeypatch.setattr(cjk_font, "is_variable_or_thin", lambda p: p.endswith("Thin.ttf"))
    assert cjk_font.resolve_static_cjk(str(thin)) == static
    assert cjk_font.resolve_static_cjk(str(static)) == static


def test_symbol_glyph_tokens_are_not_blocking():
    assert symbol_glyph_evidence("要点\n\x01 在本项II期试验中")
    assert symbol_glyph_evidence("Gu 等 \n\ufffd MG-K10")
    assert not symbol_glyph_evidence("坏\ufffd字")
    assert not symbol_glyph_evidence("a\x01b")
    assert not symbol_glyph_evidence("\x01 好\u0085")

    pages = ["要点\n\x01 在本项II期试验中\n\x01 另一条"]
    codes = {f.code: f.severity for f in check_translation_text(source_text="x", translated_text=pages[0], translated_pages=pages)}
    assert codes.get("TEXT_LAYER_SYMBOL_GLYPH") == "warning"
    assert "TEXT_ENCODING_ARTIFACT" not in codes

    bad = ["要点\n\x01 在本项II期\n坏\ufffd字"]
    codes = {f.code: f.severity for f in check_translation_text(source_text="x", translated_text=bad[0], translated_pages=bad)}
    assert codes.get("TEXT_ENCODING_ARTIFACT") == "blocker"


def _block(block_id: str, text: str) -> TranslatableBlock:
    return TranslatableBlock(
        block_id=block_id,
        source_text=text,
        translation_policy=TranslationPolicy.TRANSLATE,
        role="table_cell",
        bbox=BoundingBox(x0=0, y0=0, x1=80, y1=12),
    )


def test_digit_drift_cell_is_retried_with_fresh_id():
    blocks = [_block("c1", "placebo, (95% CI)")]
    calls: list[list[str]] = []

    def translator(payloads):
        ids = [p["id"] for p in payloads]
        calls.append(ids)
        if ids == ["c1"]:
            return {"c1": "应答者，n (%)"}  # 批量时错位：拿到了邻格的译文
        return {ids[0]: "安慰剂，(95% CI)"}

    out = translate_table_blocks(blocks, translator, drift_fallback_source=True)
    assert out["c1"].startswith("安慰剂")
    assert calls[1] == ["c1#retry"]
