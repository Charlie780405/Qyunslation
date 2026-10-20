"""PLAN-083c：真实 LLM 译文下的文献表落笔回归（数字比较、表头串改、统一字号、字形）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from qyunslation.structure.models import (  # noqa: E402
    BlockRole,
    BoundingBox,
    SourceStyle,
    TranslatableBlock,
    TranslationPolicy,
)
from qyunslation.structure.table_cell_policy import digit_tokens_preserved  # noqa: E402
from qyunslation.structure.table_translate import (  # noqa: E402
    TableTranslateError,
    translate_table_blocks,
)

SAMPLE = ROOT / "var/pipeline/runs/f3c52a20-cc99-4320-a2b8-6dc7dd303d0c/gen-1/input/10-LIT-2025-611-Trial.pdf"


def test_thin_space_and_fullwidth_parens_are_same_digits():
    assert digit_tokens_preserved("611 Group A (n\u2009=\u200930)", "611 A组（n = 30）")
    assert digit_tokens_preserved("Female (12)", "女性（12）")
    assert not digit_tokens_preserved("611 Group A (n = 30)", "A组（n = 30）")


def _block(bid: str, text: str) -> TranslatableBlock:
    return TranslatableBlock(
        block_id=bid,
        source_text=text,
        role=BlockRole.TABLE_HEADER,
        translation_policy=TranslationPolicy.TRANSLATE,
        bbox=BoundingBox(x0=0, y0=0, x1=80, y1=12),
        source_style=SourceStyle(font_size=10.0),
        row_index=0,
        column_index=1,
    )


def test_drift_fallback_keeps_source_for_cell_only():
    blocks = [_block("t:r0c1", "611 Group A (n = 30)"), _block("t:r0c2", "Placebo group (n = 32)")]

    def worker(payloads):
        return {p["id"]: ("曲罗芦单抗 Q2W" if p["id"].endswith("c1") else "安慰剂组（n = 32）") for p in payloads}

    with pytest.raises(TableTranslateError):
        translate_table_blocks(blocks, worker)
    out = translate_table_blocks(blocks, worker, drift_fallback_source=True)
    assert out["t:r0c1"] == "611 Group A (n = 30)"
    assert out["t:r0c2"] == "安慰剂组（n = 32）"


def test_tralokinumab_header_slots_not_applied_to_other_placebo_tables():
    from pdf_table_column_center import header_slots_from_blob

    assert header_slots_from_blob("611 A组（n = 30） 611 B组 安慰剂组（n = 32）", 4) == ["", "", "", ""]
    assert header_slots_from_blob("Group Placebo (N=73)", 4)[1] == ""
    assert header_slots_from_blob("曲罗芦单抗 Q2W 曲罗芦单抗 Q4W 安慰剂 Q2W", 4)[1] == "曲罗芦单抗 Q2W"


def test_helvetica_missing_glyphs_route_to_cjk_font():
    from qyunslation.structure.table_writeback import _paint_font, _script_runs

    assert _paint_font("≥ 3", bold=False)[0] == "china-ss"
    assert _paint_font("12.5 (3.2)", bold=False)[0] == "helv"
    runs = _script_runs("TEAE（≥ 5%）", bold=False)
    assert all(font == "china-ss" for font, text in runs if "≥" in text)


def test_fit_uniform_gives_one_size_per_table():
    from pdf_table_translate import _fit_uniform
    from qyunslation.structure.role_fitter import FitBlock

    blocks = [
        FitBlock("a", str(BlockRole.TABLE_HEADER), "Total (n = 93)", "总计（n = 93）", 10.0, False, 40.0, 14.0),
        FitBlock("b", str(BlockRole.TABLE_CELL), "Age, years", "年龄，岁", 10.0, False, 120.0, 14.0),
        FitBlock("c", str(BlockRole.TABLE_CELL), "46.1 (18.3)", "46.1 (18.3)", 10.0, False, 44.0, 30.0),
    ]
    results = _fit_uniform(blocks, table_size_mode="source_p75")
    sizes = {round(r.font_size, 2) for r in results}
    assert len(sizes) == 1
    assert min(sizes) >= 7.0


@pytest.mark.skipif(not SAMPLE.is_file(), reason="611 sample not present")
def test_real_611_font_size_from_spans():
    import pymupdf

    from qyunslation.structure.table_rebuild import rebuild_from_page

    doc = pymupdf.open(SAMPLE)
    result = rebuild_from_page(doc[5], (71.0, 94.0, 539.0, 300.0))
    assert result.font_size == pytest.approx(10.0, abs=0.5)
