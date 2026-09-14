# SPDX-License-Identifier: MPL-2.0
"""PLAN-049：文献表不落笔；047d 数字邻居门禁。"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from qyunslation.structure.models import (
    BlockRole,
    BoundingBox,
    ContentProfile,
    ObjectType,
    Representation,
    SourceStyle,
    TableObject,
    TranslatableBlock,
    TranslationPolicy,
)


def _cell_pdf(path: Path, *, bbox: tuple[float, float, float, float], text: str) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=500, height=300)
    page.insert_text((bbox[0] + 4, bbox[1] + 16), text, fontname="china-ss", fontsize=9)
    doc.save(path)
    doc.close()
    return path


def _lit_manifest(block: TranslatableBlock, *, table_bbox: BoundingBox) -> SimpleNamespace:
    table = TableObject.model_construct(
        type=ObjectType.TABLE,
        object_id="obj:" + "a" * 64,
        canvas_id="page:1",
        representation=Representation.VECTOR,
        semantic_id="table:1",
        translatable_blocks=[block],
        row_count=1,
        column_count=4,
        bbox=table_bbox,
    )
    return SimpleNamespace(
        objects=[table],
        extensions={},
        issues=[],
        document=SimpleNamespace(
            source_sha256="0" * 64,
            content_profile=ContentProfile.RESEARCH_ARTICLE,
        ),
        refresh_summary=lambda: None,
    )


def test_literature_wide_table_leaves_babeldoc_text(tmp_path):
    from pdf_table_translate import translate_pdf_tables

    bbox = (20, 30, 400, 80)
    src = _cell_pdf(tmp_path / "lit.pdf", bbox=bbox, text="年龄（岁） 37.1")
    block = TranslatableBlock(
        block_id="t:r0c0",
        source_text="年龄（岁）",
        role=BlockRole.TABLE_CELL,
        translation_policy=TranslationPolicy.TRANSLATE,
        bbox=BoundingBox(x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3]),
        source_style=SourceStyle(font_size=9),
        row_index=0,
        column_index=0,
    )
    table_box = BoundingBox(x0=20, y0=20, x1=420, y1=260)
    manifest = _lit_manifest(block, table_bbox=table_box)
    dest = translate_pdf_tables(
        src,
        structure_manifest=manifest,
        translator=lambda payloads: {item["id"]: "应被忽略的重画" for item in payloads},
    )
    assert dest == src
    assert not src.with_name(src.stem + ".tbltr.pdf").is_file()
    assert manifest.objects[0].reason_code == "literature_leave_babeldoc"
    text = pymupdf.open(src)[0].get_text()
    assert "年龄（岁）" in text
    assert "应被忽略的重画" not in text


def test_047d_patcher_has_numeric_guard():
    src = Path("scripts/apply-pdf2zh-047d-para-layout.py").read_text(encoding="utf-8")
    assert "_numeric_cell" in src
    assert "PLAN-049b" in src
    assert "len(t) <= 20" in src


def test_split_cells_keeps_value_groups():
    from pdf_table_column_center import split_cells

    assert split_cells("年龄（岁），均值（SD）37.1 (13.3) 38.9 (16.3) 38.3 (13.2)") == [
        "37.1 (13.3)",
        "38.9 (16.3)",
        "38.3 (13.2)",
    ]
    assert split_cells("Q2W 第52周 40阴性 90.0 1 11.2") == [
        "Q2W",
        "第52周",
        "40",
        "阴性",
        "90.0",
        "1",
        "11.2",
    ]
    vals = split_cells("IGA 4（重度）36（27.7）59（44.0）28（38）")
    assert vals[-3:] == ["36 (27.7)", "59 (44.0)", "28 (38)"]


def test_normalize_ascii_halfwidth():
    from pdf_table_column_center import normalize_ascii, prefer_origin_abbrev, split_cells

    assert normalize_ascii("36（27.7）") == "36(27.7)"
    assert normalize_ascii("＜10") == "<10"
    assert "（" not in normalize_ascii("均值（SD）")
    assert prefer_origin_abbrev("每4周", "Q4W") == "Q4W"
    assert prefer_origin_abbrev("每2周", "Q2W") == "Q2W"
    assert prefer_origin_abbrev("阴性", "Negative") == "阴性"
    assert split_cells("36（27.7）") == ["36 (27.7)"]


def test_column_center_moves_bunched_values(tmp_path):
    from pdf_table_column_center import center_table_region

    odoc = pymupdf.open()
    origin = odoc.new_page(width=500, height=160)
    origin.insert_text((20, 70), "Age (years), mean (SD)", fontsize=9)
    origin.insert_text((200, 70), "37.1 (13.3)", fontsize=9)
    origin.insert_text((320, 70), "38.9 (16.3)", fontsize=9)
    origin.insert_text((430, 70), "38.3 (13.2)", fontsize=9)
    ddoc = pymupdf.open()
    dest = ddoc.new_page(width=500, height=160)
    dest.insert_text(
        (20, 70),
        "年龄（岁），均值（SD）37.1 (13.3) 38.9 (16.3) 38.3 (13.2)",
        fontname="china-ss",
        fontsize=9,
    )
    rect = (10, 40, 490, 100)
    stats = center_table_region(dest, origin, rect)
    assert stats["moved"] >= 3
    assert stats["rows"] >= 1
    words = dest.get_text("words", clip=pymupdf.Rect(rect))
    values = [w for w in words if any(tok in w[4] for tok in ("37.1", "38.9", "38.3"))]
    assert values, dest.get_text()
    centers = sorted((w[0] + w[2]) / 2.0 for w in values)
    assert centers[0] > 180
    assert centers[-1] > 400
    text = dest.get_text()
    assert "37.1" in text and "38.9" in text and "38.3" in text
    assert "（" not in text  # 049f 半角
    odoc.close()
    ddoc.close()


def test_nrs_continuation_two_rows(tmp_path):
    """PLAN-049f：原文两行（数值行 + N= 续行）分别落在同一数据列。"""
    from pdf_table_column_center import center_table_region

    odoc = pymupdf.open()
    origin = odoc.new_page(width=520, height=200)
    # 上行
    origin.insert_text((20, 60), "Weekly pruritus", fontsize=8)
    origin.insert_text((200, 60), "7.5 (1.5),", fontsize=8)
    origin.insert_text((320, 60), "7.6 (1.5),", fontsize=8)
    origin.insert_text((430, 60), "7.7 (1),", fontsize=8)
    # 下行 N=
    origin.insert_text((20, 78), "NRS, mean (SD)", fontsize=8)
    origin.insert_text((200, 78), "N=129", fontsize=8)
    origin.insert_text((320, 78), "N=133", fontsize=8)
    origin.insert_text((430, 78), "N=73", fontsize=8)

    ddoc = pymupdf.open()
    dest = ddoc.new_page(width=520, height=200)
    dest.insert_text(
        (20, 60),
        "每周瘙痒7.5 (1.5), 7.6 (1.5), 7.7 (1),",
        fontname="china-ss",
        fontsize=8,
    )
    dest.insert_text(
        (20, 78),
        "NRS，均值（SD）aN=129N=133N=73",
        fontname="china-ss",
        fontsize=8,
    )
    rect = (10, 40, 510, 120)
    stats = center_table_region(dest, origin, rect)
    assert stats["rows"] >= 2, stats
    words = list(dest.get_text("words", clip=pymupdf.Rect(rect)))
    n_eq = [w for w in words if "129" in w[4] or "N=129" in w[4] or w[4] == "129"]
    vals = [w for w in words if "7.5" in w[4]]
    assert n_eq and vals, dest.get_text()
    # 两行 y 不同
    assert abs(((n_eq[0][1] + n_eq[0][3]) / 2) - ((vals[0][1] + vals[0][3]) / 2)) > 4
    # 纵向不严重重叠：数值行底 < N= 行顶 + 容差
    assert vals[0][3] <= n_eq[0][1] + 6
    odoc.close()
    ddoc.close()


def test_prefer_q4w_over_mei4zhou(tmp_path):
    from pdf_table_column_center import center_table_region

    odoc = pymupdf.open()
    origin = odoc.new_page(width=520, height=120)
    origin.insert_text((40, 50), "Q4W", fontsize=9)
    origin.insert_text((120, 50), "Week 52", fontsize=9)
    origin.insert_text((220, 50), "10", fontsize=9)
    origin.insert_text((280, 50), "Negative", fontsize=9)
    origin.insert_text((360, 50), "25.3", fontsize=9)
    origin.insert_text((430, 50), "2", fontsize=9)
    origin.insert_text((480, 50), "2.8", fontsize=9)
    ddoc = pymupdf.open()
    dest = ddoc.new_page(width=520, height=120)
    dest.insert_text(
        (40, 50),
        "每4周 第52周 10 阴性 25.3 2 2.8",
        fontname="china-ss",
        fontsize=9,
    )
    rect = (20, 30, 510, 90)
    stats = center_table_region(dest, origin, rect)
    assert stats["moved"] >= 4
    text = dest.get_text()
    assert "Q4W" in text
    assert "每4周" not in text
    odoc.close()
    ddoc.close()


def test_column_center_module_does_not_wipe_region():
    src = Path("scripts/pdf_table_column_center.py").read_text(encoding="utf-8")
    assert "redact_table_region" not in src
    assert "paint_fitted_blocks" not in src
    assert "normalize_ascii" in src
    assert "qy-tbl" in src
    assert "hpd_column_ranges" in src
    assert "restore_rule_lines" in src


def test_normalize_allow_translate_false_keeps_latin():
    from pdf_table_normalize import normalize_table_page

    doc = pymupdf.open()
    page = doc.new_page(width=200, height=80)
    page.insert_text((20, 40), "Week", fontname="helv", fontsize=5)
    called = []

    def translator(text):
        called.append(text)
        return "周"

    stats = normalize_table_page(
        page, (10, 10, 180, 70), translator=translator, allow_translate=False
    )
    assert called == []
    assert stats["translated"] == 0
    doc.close()


def test_hpd_units_yield_seven_columns():
    from pdf_table_column_center import column_ranges_from_hpd_units

    # 7 列中心约在 80, 150, 220, 280, 360, 440, 500
    def u(cx, text="1"):
        return (cx - 8, 40.0, cx + 8, 52.0, text)

    items = [
        [
            [u(80, "Q2W")],
            [u(150, "W52")],
            [u(220, "40")],
            [u(280, "Neg")],
            [u(360, "90")],
            [u(440, "1")],
            [u(500, "11")],
        ]
    ]
    cols = column_ranges_from_hpd_units(items, (40, 30, 540, 80), 7)
    assert len(cols) == 7
    assert cols[0][0] == 40
    assert cols[-1][1] == 540
    # 浓度列中心应落在第 5 列（0-index 4）
    assert cols[4][0] < 360 < cols[4][1]


def test_resolve_prefers_hpd_when_more_cols():
    from pdf_table_column_center import resolve_column_ranges

    odoc = pymupdf.open()
    origin = odoc.new_page(width=520, height=120)
    origin.insert_text((40, 50), "Q2W", fontsize=9)
    origin.insert_text((120, 50), "Week 52", fontsize=9)
    origin.insert_text((220, 50), "40", fontsize=9)
    origin.insert_text((280, 50), "Neg", fontsize=9)
    origin.insert_text((360, 50), "90.0", fontsize=9)
    origin.insert_text((430, 50), "1", fontsize=9)
    origin.insert_text((490, 50), "11.2", fontsize=9)
    grid = SimpleNamespace(
        error=None,
        not_a_table=False,
        n_cols=7,
        rows=[
            ["Dose", "Visit", "ADA", "nAb", "Conc", "IGA", "EASI"],
            ["Q2W", "Week 52", "40", "Neg", "90.0", "1", "11.2"],
        ],
    )
    cols, src = resolve_column_ranges(origin, (20, 30, 510, 90), grid=grid)
    assert src == "hpd"
    assert len(cols) == 7
    odoc.close()


def test_restore_rule_lines_completes_bottom():
    from pdf_table_column_center import restore_rule_lines, table_rule_lines

    odoc = pymupdf.open()
    origin = odoc.new_page(width=400, height=200)
    origin.draw_line((40, 40), (360, 40), width=0.5)
    origin.draw_line((40, 70), (360, 70), width=0.5)
    origin.draw_line((40, 160), (360, 160), width=0.5)
    ddoc = pymupdf.open()
    dest = ddoc.new_page(width=400, height=200)
    dest.draw_line((40, 40), (360, 40), width=0.5)
    dest.draw_line((40, 70), (360, 70), width=0.5)
    dest.draw_line((40, 160), (260, 160), width=0.5)  # 底线缺右段
    rect = (30, 30, 370, 170)
    n = restore_rule_lines(dest, origin, rect)
    assert n >= 3
    bottoms = [ln for ln in table_rule_lines(dest, rect) if abs(ln[2] - 160) < 1.5]
    assert bottoms
    assert max(b[1] for b in bottoms) >= 350
    odoc.close()
    ddoc.close()


def test_restore_rule_lines_keeps_first_col_stub():
    """短左段 + 长右段并成一条后，重描必须穿过第一列。"""
    from pdf_table_column_center import restore_rule_lines, table_rule_lines

    odoc = pymupdf.open()
    origin = odoc.new_page(width=600, height=200)
    origin.draw_line((67, 80), (93, 80), width=0.5)
    origin.draw_line((93, 80), (520, 80), width=0.5)
    ddoc = pymupdf.open()
    dest = ddoc.new_page(width=600, height=200)
    dest.draw_line((93, 80), (520, 80), width=0.5)
    n = restore_rule_lines(dest, origin, (90, 70, 530, 100))
    assert n >= 1
    lines = table_rule_lines(dest, (90, 70, 530, 100))
    assert lines and min(ln[0] for ln in lines) <= 68.0
    odoc.close()
    ddoc.close()


def test_header_slots_seven_cols():
    from pdf_table_column_center import header_slots_from_blob

    blob = "剂量 ADA a nAb 访视 与 抗药物抗体 曲罗芦单抗 浓度 (μg mL-1) 访视时 IGA 访视时 EASI"
    slots = header_slots_from_blob(blob, 7)
    assert slots[0] == "剂量"
    assert slots[1] == "访视"
    assert slots[2] == "ADA"
    assert slots[3] == "nAb"
    assert "浓度" in slots[4] or "曲罗" in slots[4]
    assert slots[5] == "伴ADA访视的IGA"
    assert slots[6] == "伴ADA访视的EASI"


def test_header_slots_four_cols_and_force_easi():
    from pdf_table_column_center import header_slots_from_blob

    t1 = header_slots_from_blob("曲罗芦单抗 Q2W 曲罗芦单抗 Q4W 安慰剂 Q2W", 4)
    assert t1[1] == "曲罗芦单抗 Q2W"
    assert t1[2] == "曲罗芦单抗 Q4W"
    assert t1[3] == "安慰剂 Q2W"
    forced = header_slots_from_blob("剂量 ADA nAb 访视 曲罗芦单抗", 7)
    assert forced[6] == "伴ADA访视的EASI"
    assert forced[5] == "伴ADA访视的IGA"


def test_header_n_eq_texts_from_origin():
    from pdf_table_column_center import header_n_eq_texts

    ocels = ["", "( 130) N =", "( 134) N =", "( 73) N ="]
    out = header_n_eq_texts(ocels, "", 3)
    assert out[1] == "(N=130)"
    assert out[2] == "(N=134)"
    assert out[3] == "(N=73)"
    dest = header_n_eq_texts(ocels, "( N = 130 ) ( N = 134 )( N = 73 )", 3)
    assert dest[1:] == ["(N=130)", "(N=134)", "(N=73)"]


def test_header_line_allows_q2w_drug_names():
    from pdf_table_column_center import _is_table_header_line

    ocels = ["", "Tralokinumab Q2W", "Tralokinumab Q4W", "Placebo Q2W"]
    assert _is_table_header_line(ocels, " ".join(ocels)) is True
    data = ["Q2W", "Week 52", "40", "Negative", "90.0", "1", "11.2"]
    assert _is_table_header_line(data, " ".join(data)) is False


def test_should_center_small_not_a_table():
    from pdf_table_column_center import should_center_literature_table

    box = SimpleNamespace(x0=42.5, y0=622.8, x1=234.0, y1=673.7)
    assert should_center_literature_table({"grid_source": "not_a_table"}, box) is True
    fig = SimpleNamespace(x0=40.0, y0=200.0, x1=400.0, y1=500.0)
    assert should_center_literature_table({"grid_source": "not_a_table"}, fig) is False
    assert should_center_literature_table({"grid_source": "hpd"}, fig) is True


def test_lock_visit_same_column():
    from pdf_table_column_center import lock_visit_column

    origin = ["Q4W", "Safety FU", "10", "Negative", "2.97", "NA", "NA"]
    # 误把安全性随访放进 ADA 列
    dest = ["Q4W", "第52周", "安全性随访", "阴性", "2.97", "NA", "NA"]
    out = lock_visit_column(dest, origin)
    assert out[1] in {"第52周", "安全性随访"}
    assert out[2] != "安全性随访"
    assert not any(t == "安全性随访" for i, t in enumerate(out) if i != 1)


def test_dlqi_wrap_keeps_body_size():
    from pdf_table_column_center import _BODY_MIN, _fit_cell_lines

    wide = (194.0, 326.2)
    one = _fit_cell_lines("16.0 (7.6), N = 128", wide, size=8.0, left=False)
    assert len(one) == 1
    assert "16.0" in one[0][0] and "N" in one[0][0]
    narrow = (200.0, 236.0)
    two = _fit_cell_lines("16.0 (7.6), N = 128", narrow, size=8.0, left=False)
    assert len(two) == 2
    assert "16.0" in two[0][0]
    assert "N" in two[1][0]
    assert all(fs >= _BODY_MIN for _t, _x, fs in two)
    jammed = _fit_cell_lines(
        "16.0 (7.6), N = 128", narrow, size=8.0, left=False, max_dy=2.0
    )
    assert len(jammed) == 1


def test_column_center_uses_unified_font(tmp_path):
    from pdf_table_column_center import _FONTNAME, _FONT_PATH, center_table_region

    odoc = pymupdf.open()
    origin = odoc.new_page(width=500, height=160)
    origin.insert_text((20, 70), "Age (years), mean (SD)", fontsize=9)
    origin.insert_text((200, 70), "37.1 (13.3)", fontsize=9)
    origin.insert_text((320, 70), "38.9 (16.3)", fontsize=9)
    origin.insert_text((430, 70), "38.3 (13.2)", fontsize=9)
    ddoc = pymupdf.open()
    dest = ddoc.new_page(width=500, height=160)
    dest.insert_text(
        (20, 70),
        "年龄（岁），均值（SD）37.1 (13.3) 38.9 (16.3) 38.3 (13.2)",
        fontname="china-ss",
        fontsize=9,
    )
    stats = center_table_region(dest, origin, (10, 40, 490, 100))
    assert stats["moved"] >= 3
    fonts = set()
    for block in (dest.get_text("dict") or {}).get("blocks") or []:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            for span in line.get("spans") or []:
                fonts.add(span.get("font"))
    if _FONT_PATH.is_file():
        assert any(_FONTNAME in str(f) or "Noto" in str(f) or "qy" in str(f).lower() for f in fonts)
    odoc.close()
    ddoc.close()


def test_sanitize_cols_drops_inverted():
    from pdf_table_column_center import _sanitize_cols

    cols = [(70.0, 196.7), (196.7, 327.6), (327.6, 437.5), (437.5, 534.7), (534.7, 520.0)]
    out = _sanitize_cols(cols)
    assert len(out) == 4
    assert out[-1][1] > out[-1][0]


def test_consume_data_row_sequential():
    from pdf_table_column_center import consume_data_row

    blob = "年龄 37.1 (13.3) 38.9 (16.3) 38.3 (13.2) 男性 74 (56.9) 68 (50.7) 41 (56)"
    ocels = ["Age", "37.1 (13.3)", "38.9 (16.3)", "38.3 (13.2)"]
    texts, rest = consume_data_row(blob, ocels)
    assert texts is not None
    assert texts[1] == "37.1 (13.3)"
    assert "38.3" in texts[3]
    texts2, _rest2 = consume_data_row(rest, ["Male", "74 (56.9)", "68 (50.7)", "41 (56)"])
    assert texts2 is not None
    assert texts2[1].startswith("74")


def test_assign_keeps_easi_and_visit():
    from pdf_table_column_center import _assign, lock_visit_column

    ocels = ["Q2W", "Week 52", "40", "Negative", "90.0", "1", "11.2"]
    texts = _assign(ocels, "Q2W 第52周 40 阴性 90.0 1 11.2")
    assert texts is not None
    texts = lock_visit_column(texts, ocels)
    assert texts[1] == "第52周"
    assert texts[-1] == "11.2"


def test_header_n_eq_survives_neighbor_redact():
    from pdf_table_column_center import center_table_region

    odoc = pymupdf.open()
    origin = odoc.new_page(width=500, height=180)
    origin.insert_text((200, 68), "Tralokinumab Q2W", fontsize=8)
    origin.insert_text((320, 68), "Tralokinumab Q4W", fontsize=8)
    origin.insert_text((430, 68), "Placebo Q2W", fontsize=8)
    origin.insert_text((200, 80), "(N=130)", fontsize=8)
    origin.insert_text((320, 80), "(N=134)", fontsize=8)
    origin.insert_text((430, 80), "(N=73)", fontsize=8)
    origin.insert_text((20, 100), "Age, years", fontsize=8)
    origin.insert_text((200, 100), "37.1 (13.3)", fontsize=8)
    origin.insert_text((320, 100), "38.9 (16.3)", fontsize=8)
    origin.insert_text((430, 100), "38.3 (13.2)", fontsize=8)
    ddoc = pymupdf.open()
    dest = ddoc.new_page(width=500, height=180)
    dest.insert_text(
        (20, 68),
        "曲罗芦单抗 Q2W 曲罗芦单抗 Q4W 安慰剂 (N=130)(N=134)(N=73)",
        fontname="china-ss",
        fontsize=8,
    )
    dest.insert_text(
        (20, 100),
        "年龄 37.1 (13.3) 38.9 (16.3) 38.3 (13.2)",
        fontname="china-ss",
        fontsize=8,
    )
    stats = center_table_region(dest, origin, (10, 50, 490, 120))
    assert stats["moved"] >= 3
    blob = dest.get_text()
    assert "N=130" in blob.replace(" ", "")
    odoc.close()
    ddoc.close()


def test_split_cells_unglues_table3_decimals():
    from pdf_table_column_center import pretreat_row, split_cells

    # 90.0+1+11.2 粘连 → 90.0111.2
    glued = "Q2W第52周40阴性90.0111.2"
    toks = split_cells(glued)
    assert "Q2W" in toks
    assert "第52周" in toks
    assert "40" in toks
    assert "阴性" in toks
    assert "90.0" in toks
    assert "1" in toks
    assert "11.2" in toks
    assert not any(re.search(r"\d+\.\d{3,}", t) for t in toks)
    assert pretreat_row("90.0111.2") == "90.0 1 11.2"
    assert pretreat_row("20.422.3") == "20.4 2 2.3"


def test_assign_by_origin_shapes_table3_row():
    from pdf_table_column_center import assign_by_origin_shapes, prefer_origin_abbrev

    ocels = ["Q2W", "Week 52", "40", "Negative", "90.0", "1", "11.2"]
    out = assign_by_origin_shapes(ocels, "Q2W第52周40阴性90.0111.2")
    assert out is not None
    assert out[0] == "Q2W"
    assert out[1] == "第52周"
    assert out[2] == "40"
    assert out[3] == "阴性"
    assert out[4] == "90.0"
    assert out[5] == "1"
    assert out[6] == "11.2"
    out2 = assign_by_origin_shapes(
        ["Q4W", "Week 52", "40", "Negative", "20.4", "2", "2.3"],
        "Q4W第52周40阴性20.422.3",
    )
    assert out2 is not None
    assert out2[4:] == ["20.4", "2", "2.3"]
    assert prefer_origin_abbrev("每4周", "Q4W") == "Q4W"


def test_replay_ffc3_mono_table3_seven_cols():
    """现网作业 ffc3 mono 表3：七列居中，无三位小数粘连 token。"""
    import shutil

    from pdf_table_column_center import center_table_region

    job = Path("/home/dev/pdf2zh/pdf2zh_files/ffc3aa5e-b7f3-4955-9470-b59334367fdf")
    mono = job / "ljae439.no_watermark.zh-CN.mono.pdf"
    origin_pdf = job / "ljae439.pdf"
    if not mono.is_file() or not origin_pdf.is_file():
        import pytest

        pytest.skip("ffc3 job artifacts not present")
    out = Path("/tmp/test-ffc3-049j-table3.pdf")
    shutil.copy(mono, out)
    odoc = pymupdf.open(origin_pdf)
    ddoc = pymupdf.open(out)
    rect = (60, 70, 530, 245)
    stats = center_table_region(ddoc[6], odoc[6], rect)
    assert stats.get("moved", 0) >= 70
    ddoc.saveIncr()
    ddoc.close()
    odoc.close()
    ddoc = pymupdf.open(out)
    spans = []
    clip = pymupdf.Rect(55, 70, 545, 255)
    for block in (ddoc[6].get_text("dict", clip=clip) or {}).get("blocks") or []:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            for sp in line.get("spans") or []:
                t = (sp.get("text") or "").strip()
                if not t:
                    continue
                bb = sp["bbox"]
                spans.append(((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0, t))
    ddoc.close()
    assert not any(re.search(r"\d+\.\d{3,}", t) for _, _, t in spans)
    texts = {t for _, _, t in spans}
    assert "90.0" in texts
    assert "11.2" in texts
    assert "20.4" in texts
    assert "2.3" in texts
    iga = [cx for cx, cy, t in spans if cy < 110 and "伴ADA访视的IGA" in t]
    easi = [cx for cx, cy, t in spans if cy < 110 and "伴ADA访视的EASI" in t]
    assert iga and easi and abs(iga[0] - easi[0]) > 20
    visit_alone = [
        cx
        for cx, cy, t in spans
        if cy < 110
        and (t == "访视" or (t.startswith("访视") and "IGA" not in t and "EASI" not in t))
    ]
    assert visit_alone
    assert max(visit_alone) < 200
    assert not any(
        cy > 230 and (t == "访视" or "伴ADA访视的" in t or t in {"剂量", "剂量"})
        for _, cy, t in spans
    )


def test_header_slots_six_cols_force_seven_defaults():
    from pdf_table_column_center import _header_skip_cell, header_slots_from_blob

    slots = header_slots_from_blob("剂量 ADA nAb 曲罗芦单抗", 6)
    assert slots[0] == "剂量"
    assert slots[1] == "访视"
    assert slots[5] == "伴ADA访视的IGA"
    assert _header_skip_cell("A") is True
    assert _header_skip_cell("a") is True
    assert _header_skip_cell("with ADA") is True
    assert _header_skip_cell("at visit with ADA") is True


def test_ada7_header_merge_once_no_duplicate_dose():
    from pdf_table_column_center import (
        header_slots_from_blob,
        header_texts_from_merged,
        merge_origin_header_cells,
    )

    cols = [(0, 40), (40, 90), (90, 120), (120, 150), (150, 230), (230, 300), (300, 370)]

    def sp(x0, x1, y0, y1, text):
        return {
            "bbox": (x0, y0, x1, y1),
            "cx": (x0 + x1) / 2,
            "cy": (y0 + y1) / 2,
            "text": text,
            "size": 8.0,
        }

    top = [
        sp(160, 220, 0, 8, "Tralokinumab"),
        sp(240, 290, 0, 8, "IGA at visit"),
        sp(310, 360, 0, 8, "EASI at visit"),
    ]
    bot = [
        sp(2, 38, 10, 18, "Dose"),
        sp(42, 88, 10, 18, "Visit with ADA"),
        sp(92, 118, 10, 18, "ADA"),
        sp(122, 148, 10, 18, "nAb"),
        sp(152, 228, 10, 18, "concentration (μg mL-1)"),
        sp(232, 298, 10, 18, "with ADA"),
        sp(302, 368, 10, 18, "with ADA"),
    ]
    merged = merge_origin_header_cells([top, bot], cols)
    assert "Dose" in merged[0]
    assert "Visit" in merged[1]
    slots = header_slots_from_blob(" ".join(merged), 7)
    texts = header_texts_from_merged(merged, slots)
    assert texts.count("剂量") == 1
    assert texts[0] == "剂量"
    assert texts[1] == "访视"
    assert texts[6] == "伴ADA访视的EASI"
    assert texts[5] == "伴ADA访视的IGA"


def test_footnote_line_is_not_header():
    from pdf_table_column_center import _is_table_footnote_line, _is_table_header_line

    ocels = [
        "EASI E",
        "A d S it",
        "I d FU f ll",
        "IGA I ti t",
        "Gl b l A t",
        "NA t li bl",
        "Ab t li i",
    ]
    otext = "EASI Eczema Area and Severity Index FU follow-up IGA Investigator"
    assert _is_table_footnote_line(ocels, otext) is True
    assert _is_table_header_line(ocels, otext) is False
