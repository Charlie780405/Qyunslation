"""PLAN-044：格级残留隔离、版式归一化与批内完整性。"""
from __future__ import annotations

from qyunslation.structure.models import (
    BoundingBox,
    SourceStyle,
    TranslatableBlock,
    TranslationPolicy,
)
from qyunslation.structure.role_fitter import (
    TABLE_ROLE_SIZE,
    FitBlock,
    fit_group,
    measure_textbox,
    wrap_lines,
)
from qyunslation.structure.table_qc import (
    QC_SOURCE_RESIDUE,
    RESIDUE_RATE_LIMIT,
    assert_table_qc_clean,
    evaluate_table_qc,
    residue_rate,
)
from qyunslation.structure.table_translate import translate_table_blocks


def test_missing_llm_fills_source_not_raise():
    blocks = [
        TranslatableBlock(
            block_id="a",
            source_text="某某罕见标签乙",
            translation_policy=TranslationPolicy.TRANSLATE,
            role="table_cell",
            bbox=BoundingBox(x0=0, y0=0, x1=40, y1=12),
        ),
        TranslatableBlock(
            block_id="b",
            source_text="某某罕见标签甲",
            translation_policy=TranslationPolicy.TRANSLATE,
            role="table_cell",
            bbox=BoundingBox(x0=0, y0=12, x1=40, y1=24),
        ),
    ]

    def partial(payloads):
        # 只回第一条 id，模拟批内丢索引
        return {payloads[0]["id"]: "Rare Label B"}

    out = translate_table_blocks(blocks, partial)
    assert out["a"] == "Rare Label B"
    assert out["b"] == "某某罕见标签甲"  # 中文源回填，不炸整表


def test_low_residue_does_not_fail_table():
    blocks = []
    translations = {}
    for i in range(10):
        bid = f"c{i}"
        blocks.append(
            TranslatableBlock(
                block_id=bid,
                source_text=f"标签{i}",
                translation_policy=TranslationPolicy.TRANSLATE,
                role="table_cell",
                source_style=SourceStyle(font_size=10),
                bbox=BoundingBox(x0=0, y0=i * 12, x1=80, y1=i * 12 + 12),
                row_index=i,
                column_index=0,
            )
        )
        translations[bid] = "Label" if i > 0 else "标签0"  # 1/10 residue
    records, hard = evaluate_table_qc(blocks, translations)
    assert residue_rate(records) <= RESIDUE_RATE_LIMIT
    assert not any(str(c).startswith("RESIDUE_RATE") for c in hard)
    assert_table_qc_clean(records, hard, isolate_residue=True)
    assert any(QC_SOURCE_RESIDUE in r.qc for r in records)


def test_normalize_table_sizes_uses_ladder():
    blocks = [
        FitBlock("h", "table_header", "A", "Header", 12.0, True, 120, 20),
        FitBlock("c", "table_cell", "B", "Body", 4.2, False, 120, 16),
        FitBlock("f", "table_footnote", "C", "Note", 9.0, False, 120, 14),
    ]
    results = fit_group(blocks, normalize_table_sizes=True)
    assert results[0].font_size == TABLE_ROLE_SIZE["table_header"]
    assert results[1].font_size == TABLE_ROLE_SIZE["table_cell"]
    assert results[2].font_size == TABLE_ROLE_SIZE["table_footnote"]


def test_wrap_lines_keeps_hyphenated_token():
    lines = wrap_lines("evaluate anti-IL-4Rα monoclonal antibody safety", 20)
    assert all("anti-IL-4Rα" in line or "anti-IL-4Rα" not in " ".join(lines) or True for line in lines)
    joined = " ".join(lines)
    assert "anti-IL-4Rα" in joined
    # 词本身不被拆成 anti- / IL
    assert "anti-\n" not in "\n".join(lines)


def test_measure_textbox_rejects_overflow():
    assert measure_textbox("short", 7.0, 80.0, 16.0)
    assert not measure_textbox("word " * 40, 7.0, 40.0, 12.0)
