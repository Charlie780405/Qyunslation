# SPDX-License-Identifier: MPL-2.0
"""PLAN-048：HPD 网格 / 对齐 / 闸门 单测（无实样 PDF）。"""
from __future__ import annotations

from qyunslation.structure.table_grid_hpd import (
    _delatex,
    _merge_wrapped_rows,
    normalize_for_align,
    parse_hpd_grid_markdown,
)
from qyunslation.structure.table_qc import (
    QC_NOT_A_TABLE,
    coverage_ok,
    cross_check,
    evaluate_hpd_gates,
    literature_paint_safe,
    looks_collapsed,
)
from qyunslation.structure.models import BoundingBox, TranslatableBlock
from qyunslation.structure.table_structure import (
    align_hpd_grid,
    data_row_gutters,
    gutter_column_centers,
)
from qyunslation.structure.table_structure import TableLocalFrame


def test_delatex_ada_superscript():
    raw = r"\( {\mathrm{{ADA}}}^{\mathrm{a}} \)"
    assert normalize_for_align(_delatex(raw)) == "adaa"


def test_merge_wrapped_rows_n_eq():
    rows = [
        ["Weekly average", "7.5 (1.5),", "7.6 (1.5),", "7.7 (1),"],
        ["NRS, mean (SD)a", "N=129", "N=133", "N=73"],
    ]
    spans = [[1, 1, 1, 1], [1, 1, 1, 1]]
    merged, _ = _merge_wrapped_rows(rows, spans)
    assert len(merged) == 1
    assert "N=129" in merged[0][1]


def test_parse_hpd_not_a_table():
    md = "Predictive factor of IGA\nEASI 90 at week 16"
    grid = parse_hpd_grid_markdown(md)
    assert grid.not_a_table is True


def test_parse_hpd_html_table():
    md = (
        "<table><tr><td>A</td><td>B</td><td>C</td></tr>"
        "<tr><td>1</td><td>2</td><td>3</td></tr>"
        "<tr><td>4</td><td>5</td><td>6</td></tr></table>"
    )
    grid = parse_hpd_grid_markdown(md)
    assert grid.not_a_table is False
    assert grid.n_cols == 3
    assert grid.n_rows == 3


def test_near_token_q2w_ocr():
    from qyunslation.structure.table_structure import _near_token

    assert _near_token("q2w", "o2w") is True
    assert _near_token("q4w", "o4w") is True
    assert _near_token("negative", "positive") is False


def test_align_merges_n_eq_wrap_line():
    """表1：药名行 + (N=) 碎片行应对齐到同一 HPD 行。"""
    names = [
        (10, 0, 80, 10, "Tralokinumab Q2W"),
        (100, 0, 170, 10, "Tralokinumab Q4W"),
        (190, 0, 250, 10, "Placebo Q2W"),
    ]
    neq = [
        (12, 12, 28, 20, "("),
        (30, 12, 38, 20, "N"),
        (40, 12, 46, 20, "="),
        (48, 12, 78, 20, "130)"),
        (102, 12, 118, 20, "("),
        (120, 12, 128, 20, "N"),
        (130, 12, 136, 20, "="),
        (138, 12, 168, 20, "134)"),
        (192, 12, 208, 20, "("),
        (210, 12, 218, 20, "N"),
        (220, 12, 226, 20, "="),
        (228, 12, 248, 20, "73)"),
    ]
    hpd = [
        ["", "Rerandomization at week 16", "", ""],
        ["", "Tralokinumab Q2W (N=130)", "Tralokinumab Q4W (N=134)", "Placebo Q2W (N=73)"],
    ]
    cells, rate, qc = align_hpd_grid(
        [ [(10, -12, 180, -2, "Rerandomization at week 16")], names, neq],
        hpd,
        mismatch_limit=0.2,
    )
    assert "HPD_GRID_MISMATCH" not in qc
    texts = [
        "".join(u[4] for u in col)
        for col in cells[1]
    ]
    assert "Tralokinumab Q2W" in texts[1] and "130" in texts[1]
    assert "134" in texts[2] and "73" in texts[3]
    assert rate < 0.25


def test_align_merges_header_wrap():
    top = [
        (210, 0, 270, 8, "Tralokinumab"),
        (370, 0, 430, 8, "IGA at visit"),
        (450, 0, 510, 8, "EASI at visit"),
    ]
    bot = [
        (10, 10, 40, 18, "Dose"),
        (50, 10, 110, 18, "Visit with ADA"),
        (120, 10, 150, 18, "ADA"),
        (152, 10, 158, 18, "a"),
        (160, 10, 190, 18, "nAb"),
        (200, 10, 280, 18, "concentration ("),
        (282, 10, 290, 18, "µ"),
        (292, 10, 320, 18, "g mL"),
        (322, 10, 340, 18, "-1"),
        (342, 10, 350, 18, ")"),
        (380, 10, 420, 18, "with ADA"),
        (460, 10, 500, 18, "with ADA"),
    ]
    hpd = [[
        "Dose",
        "Visit with ADA",
        "ADA*",
        "nAb",
        "Tralokinumab concentration (μg mL-1)",
        "IGA at visit with ADA",
        "EASI at visit with ADA",
    ]]
    cells, rate, qc = align_hpd_grid([top, bot], hpd, mismatch_limit=0.25)
    joined = ["".join(u[4] for u in col) for col in cells[0]]
    assert joined[0] == "Dose"
    assert "nAb" in joined[3]
    assert "concentration" in joined[4] and "Tralokinumab" in joined[4]
    assert "IGA" in joined[5]
    assert rate < 0.3


def test_literature_paint_safe_rejects_fragments_not_complete_n():
    ok = [
        TranslatableBlock(
            block_id="a",
            source_text="(N=130)",
            role="table_cell",
            bbox=BoundingBox(x0=10, y0=10, x1=40, y1=18),
            row_index=0,
            column_index=1,
        ),
        TranslatableBlock(
            block_id="b",
            source_text="37.1 (13.3)",
            role="table_cell",
            bbox=BoundingBox(x0=50, y0=20, x1=90, y1=28),
            row_index=1,
            column_index=1,
        ),
    ]
    assert literature_paint_safe(ok) is True
    bad = [
        TranslatableBlock(
            block_id="c",
            source_text="( N = 130) ( N =",
            role="table_cell",
            bbox=BoundingBox(x0=10, y0=10, x1=80, y1=18),
            row_index=0,
            column_index=1,
        )
    ]
    assert literature_paint_safe(bad) is False


def test_q2w_cell_is_preserved():
    from qyunslation.structure.models import TranslationPolicy
    from qyunslation.structure.table_cell_policy import classify_cell_policy
    from qyunslation.structure.table_translate import translate_table_blocks

    assert classify_cell_policy("Q2W") is TranslationPolicy.PRESERVE
    blocks = [
        TranslatableBlock(
            block_id="d",
            source_text="Q2W",
            role="table_cell",
            translation_policy=TranslationPolicy.PRESERVE,
        )
    ]
    out = translate_table_blocks(blocks, lambda payloads: {_["id"]: "每2周一次（Q2W）" for _ in payloads})
    assert out["d"] == "Q2W"


def test_align_hpd_grid_prefix():
    # 碎片 unit 对齐到 HPD 合成格
    lines = [
        [
            (0, 0, 40, 10, "Tralokinumab Q2W"),
            (42, 0, 48, 10, "("),
            (50, 0, 58, 10, "N"),
            (60, 0, 66, 10, "="),
            (68, 0, 90, 10, "130)"),
        ]
    ]
    hpd = [["Tralokinumab Q2W (N=130)"]]
    cells, rate, qc = align_hpd_grid(lines, hpd, mismatch_limit=0.2)
    assert len(cells) == 1
    assert len(cells[0][0]) == 5
    assert rate < 0.2


def test_cross_check_and_collapsed():
    rows = [
        ["Visit", "ADA", "nAb", "conc"],
        ["Week 52", "40", "Negative", "90.0"],
        ["Week 52", "20", "Negative", "121"],
        ["Safety FU", "10", "Negative", "2.97"],
    ]
    text = "Week 52 40 Negative 90.0 20 121 Safety FU 10 2.97"
    assert cross_check(rows, text) is True
    assert looks_collapsed(rows) is False
    assert coverage_ok(rows, text, floor=0.28) is True
    assert evaluate_hpd_gates(rows, text) == []


def test_looks_collapsed_first_col():
    rows = [
        ["all the text dumped here", "", "", ""],
        ["another long blob", "", "", ""],
        ["third", "", "", ""],
    ]
    assert looks_collapsed(rows) is True


def test_gutter_columns_synthetic():
    # 三列墨迹簇，中间有空隙
    lines = [
        [(10, 0, 30, 8, "Age"), (80, 0, 100, 8, "37.1"), (150, 0, 170, 8, "38.9")],
        [(10, 12, 30, 20, "Male"), (80, 12, 100, 20, "74"), (150, 12, 170, 20, "68")],
        [(10, 24, 40, 32, "BSA"), (80, 24, 100, 32, "44"), (150, 24, 170, 32, "45")],
    ]
    frame = TableLocalFrame(x0=0, y0=0, width=200, height=40, rotation=0)
    centers = gutter_column_centers(lines, frame, min_gutter=4.0)
    assert len(centers) == 3
    gutters = data_row_gutters(lines, frame, min_gutter=4.0)
    assert len(gutters) == 2


def test_gates_empty_is_not_a_table():
    assert QC_NOT_A_TABLE in evaluate_hpd_gates([], "anything")


def test_expand_cell_bboxes_widens_narrow_ink():
    from qyunslation.structure.table_structure import StructuredTableCell, expand_cell_bboxes
    from qyunslation.structure.tables import TableRegion

    region = TableRegion(number=1, x0=0, y0=0, x1=200, y1=40, line_count=2)
    cells = [
        StructuredTableCell(
            block_id="a", role="table_cell", text="Q2W",
            row_index=0, column_index=0, bbox=(10, 10, 30, 18),
        ),
        StructuredTableCell(
            block_id="b", role="table_cell", text="1",
            row_index=0, column_index=1, bbox=(90, 10, 96, 18),
        ),
        StructuredTableCell(
            block_id="c", role="table_cell", text="11.2",
            row_index=0, column_index=2, bbox=(150, 10, 170, 18),
        ),
    ]
    out = expand_cell_bboxes(cells, region)
    by_id = {c.block_id: c for c in out}
    w = by_id["b"].bbox[2] - by_id["b"].bbox[0]
    assert w > 20, w


def test_paint_short_cell_writes_visible_text():
    import pymupdf
    from qyunslation.structure.models import BoundingBox
    from qyunslation.structure.table_writeback import paint_cell

    doc = pymupdf.open()
    page = doc.new_page()
    paint_cell(
        page,
        BoundingBox(x0=10, y0=10, x1=140, y1=19.5),
        "Age (years), mean (SD)",
        bold=False,
        font_size=7.5,
        role="table_cell",
    )
    assert "Age" in (page.get_text("text") or "")
    doc.close()


def test_paint_cell_skips_sideways_for_number():
    import pymupdf
    from qyunslation.structure.models import BoundingBox
    from qyunslation.structure.table_writeback import paint_cell

    doc = pymupdf.open()
    page = doc.new_page()
    # 窄数字格：旧阈值会 rotate=90
    paint_cell(
        page,
        BoundingBox(x0=10, y0=10, x1=22, y1=28),
        "1",
        bold=False,
        font_size=8,
        role="table_cell",
    )
    text = page.get_text("text") or ""
    assert "1" in text
    doc.close()
