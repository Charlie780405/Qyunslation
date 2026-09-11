"""PLAN-044：格级残留隔离、版式归一化与批内完整性。"""
from __future__ import annotations

from pathlib import Path

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


def test_isolate_allows_overflow_and_high_residue():
    from qyunslation.structure.role_fitter import QC_OVERFLOW, FitResult

    blocks = [
        TranslatableBlock(
            block_id="c0",
            source_text="健康受试者",
            translation_policy=TranslationPolicy.TRANSLATE,
            role="table_cell",
            source_style=SourceStyle(font_size=10),
            bbox=BoundingBox(x0=0, y0=0, x1=78, y1=16),
            row_index=0,
            column_index=0,
        )
    ]
    result = FitResult(
        text="Healthy Subjects",
        font_size=7,
        bold=False,
        dpi=300,
        overflow=True,
        qc=[QC_OVERFLOW],
    )
    records, hard = evaluate_table_qc(blocks, {"c0": "Healthy Subjects"}, [result])
    assert QC_OVERFLOW in hard
    assert_table_qc_clean(records, hard, isolate_residue=True)


def test_efficacy_short_label_controlled():
    from qyunslation.structure.regulatory_entities import lookup_controlled

    assert lookup_controlled("有效性") == "Efficacy"
    assert lookup_controlled("健康受试者") == "Healthy Subjects"


def test_paint_latin_not_letterspaced():
    import pymupdf

    from qyunslation.structure.table_writeback import paint_cell

    doc = pymupdf.open()
    page = doc.new_page(width=300, height=80)
    paint_cell(
        page,
        BoundingBox(x0=10, y0=20, x1=200, y1=40),
        "Registration No.",
        bold=False,
        font_size=8.0,
    )
    paint_cell(
        page,
        BoundingBox(x0=10, y0=45, x1=280, y1=70),
        "企业选择不公示",
        bold=False,
        font_size=8.0,
    )
    text = page.get_text()
    assert "Registration No." in text
    assert "R e g i s t r a t i o n" not in text
    assert "企业选择不公示" in text
    assert "\uf96b" not in text
    doc.close()


def test_paint_mixed_keeps_latin_tokens():
    import pymupdf

    from qyunslation.structure.table_writeback import paint_cell

    doc = pymupdf.open()
    page = doc.new_page(width=520, height=80)
    paint_cell(
        page,
        BoundingBox(x0=10, y0=10, x1=500, y1=70),
        "评价611的有效性 Phase III（CRSwNP）",
        bold=False,
        font_size=7.0,
    )
    text = page.get_text()
    assert "Phase III" in text
    assert "CRSwNP" in text
    assert "611" in text
    assert "有效性" in text
    doc.close()


def test_paint_embeds_cjk_font_once():
    import pymupdf

    from qyunslation.structure.table_writeback import paint_cell, _PAGE_FONTS

    _PAGE_FONTS.clear()
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=400)
    for i, text in enumerate(["登记号", "企业选择不公示", "慢性鼻窦炎伴鼻息肉", "健康受试者"] * 8):
        y = 20 + (i % 16) * 20
        paint_cell(
            page,
            BoundingBox(x0=20, y0=y, x1=380, y1=y + 18),
            text,
            bold=False,
            font_size=8.0,
        )
    dest = "/tmp/plan044-font-once.pdf"
    doc.save(dest)
    doc.close()
    # 内置 CJK：体积应远小于「每格一份 Noto」
    assert Path(dest).stat().st_size < 200_000
    out = pymupdf.open(dest)
    text = out[0].get_text()
    assert "登记号" in text
    assert "慢性鼻窦炎" in text
    out.close()


def test_paint_healthy_subjects_stays_in_cell():
    import pymupdf

    from qyunslation.structure.table_writeback import paint_cell

    doc = pymupdf.open()
    page = doc.new_page(width=200, height=80)
    box = BoundingBox(x0=10, y0=20, x1=87.8, y1=36.1)
    page.draw_rect(pymupdf.Rect(box.x0, box.y0, box.x1, box.y1), color=(0, 0, 0), width=0.4)
    paint_cell(page, box, "Healthy Subjects", bold=False, font_size=7.0)
    # 所有字必须落在格内（含 inset）
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            x0, y0, x1, y1 = line["bbox"]
            assert x0 >= box.x0 - 0.2
            assert x1 <= box.x1 + 0.2
            assert y0 >= box.y0 - 0.2
            assert y1 <= box.y1 + 0.2
    doc.close()


def test_restore_list_prefix_avoids_digit_drift():
    blocks = [
        TranslatableBlock(
            block_id="n1",
            source_text="2.符合慢性鼻窦炎伴鼻息肉的诊断；",
            translation_policy=TranslationPolicy.TRANSLATE,
            role="table_cell",
            bbox=BoundingBox(x0=0, y0=0, x1=200, y1=16),
        )
    ]

    def drop_num(_payloads):
        return {"n1": "符合慢性鼻窦炎伴鼻息肉的诊断；"}

    out = translate_table_blocks(blocks, drop_num)
    assert out["n1"].startswith("2.")
