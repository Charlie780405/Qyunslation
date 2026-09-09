"""PLAN-030d Task 8：表格区域检测与保护。

范围已从「原位重建」降级为「区域保护」——PyMuPDF find_tables() 在无竖线的
学术三线表上不可用（详见 PLAN-030d Task 8 的探底表）。这里只验证区域被可靠
圈定、表内文字不漏进正文、不产生假阳性，不验证单元格结构。
"""
from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from qyunslation.structure import PdfStructureScanner
from qyunslation.structure.layout import body_blocks, figure_table_rects
from qyunslation.structure.models import ObjectType
from qyunslation.structure.tables import (
    ROW_GAP_BREAK_FRAC,
    TableRegion,
    _horizontal_lines,
    table_exclusion_rects,
    table_regions,
)

ROOT = Path(__file__).resolve().parents[2]
LJAE = ROOT / "tests/fixtures/structure/reference/ljae439.pdf"
NATURE = ROOT / "tests/fixtures/structure/reference/nature_comm_53384.pdf"

# 页码 -> 该页应圈定的表号，人工核对题注与横线几何得出
EXPECTED = {
    LJAE: {5: [1, 2], 7: [3]},
    NATURE: {4: [1], 5: [2], 9: [3]},
}


@pytest.fixture(scope="module")
def ljae_manifest():
    return PdfStructureScanner().scan(LJAE)


@pytest.fixture(scope="module")
def nature_manifest():
    return PdfStructureScanner().scan(NATURE)


def _regions_by_page(path: Path) -> dict[int, list[int]]:
    doc = pymupdf.open(path)
    try:
        return {
            pno: [r.number for r in table_regions(page)]
            for pno, page in enumerate(doc, 1)
            if table_regions(page)
        }
    finally:
        doc.close()


@pytest.mark.parametrize("path", [LJAE, NATURE], ids=["ljae439", "nature"])
def test_every_captioned_table_is_delimited(path):
    assert _regions_by_page(path) == EXPECTED[path]


@pytest.mark.parametrize("path", [LJAE, NATURE], ids=["ljae439", "nature"])
def test_no_false_positive_tables_on_figure_pages(path):
    """图表页的线框再多也不该被当成表格——区域必须由表题注锚定。"""
    detected = set(_regions_by_page(path))

    assert detected == set(EXPECTED[path])


def test_pages_without_table_captions_yield_no_regions():
    """Nature p7/p8/p10-p12 无表题注，find_tables() 却在这些页测出多个空表。"""
    doc = pymupdf.open(NATURE)
    try:
        for pno in (7, 8, 10, 11, 12):
            assert table_regions(doc[pno - 1]) == []
    finally:
        doc.close()


def test_table_region_covers_actual_table_content():
    doc = pymupdf.open(LJAE)
    try:
        page = doc[4]
        region = table_regions(page)[0]
        text = page.get_textbox(
            pymupdf.Rect(region.x0, region.y0, region.x1, region.y1)
        )
    finally:
        doc.close()

    assert "Tralokinumab Q2W" in text
    assert "Age (years), mean (SD)" in text


def test_segmented_rule_lines_are_merged():
    """ljae439 p5 的顶线被切成三段，必须合成一条。"""
    doc = pymupdf.open(LJAE)
    try:
        lines = _horizontal_lines(doc[4])
    finally:
        doc.close()

    ys = [round(y, 1) for _, _, y in lines]
    assert len(ys) == len(set(ys))


def test_footer_rule_is_excluded_by_gap_break():
    """Nature 每页底部 0.954 处有页脚线，不得并入表格区域。"""
    doc = pymupdf.open(NATURE)
    try:
        page = doc[4]
        height = page.rect.height
        region = table_regions(page)[0]
    finally:
        doc.close()

    assert region.y1 / height < 0.70


def test_table_1_extends_to_its_bottom_rule():
    """ljae439 p5 的 Table 1 底线在 0.287，阈值不能把它切在表头线处。"""
    doc = pymupdf.open(LJAE)
    try:
        page = doc[4]
        height = page.rect.height
        region = table_regions(page)[0]
    finally:
        doc.close()

    assert region.y1 / height == pytest.approx(0.287, abs=0.01)


def test_body_no_longer_leaks_table_content(nature_manifest):
    """Task 6 遗留：Nature p5 的 Table 2 内容曾有 27 块混入正文。"""
    p5 = [
        o
        for o in nature_manifest.objects
        if o.type is ObjectType.BODY and o.canvas_id == "page:5"
    ]

    assert len(p5) < 10


def test_table_geometry_missing_issue_is_gone(nature_manifest, ljae_manifest):
    for manifest in (nature_manifest, ljae_manifest):
        assert "TABLE_GEOMETRY_MISSING" not in {i.code for i in manifest.issues}


@pytest.mark.parametrize(
    "fixture_name,figures,tables",
    [("ljae_manifest", 5, 3), ("nature_manifest", 7, 3)],
)
def test_semantic_counts_unchanged_by_table_protection(
    request, fixture_name, figures, tables
):
    manifest = request.getfixturevalue(fixture_name)

    assert manifest.summary.figure_count == figures
    assert manifest.summary.table_count == tables


def test_tables_are_not_misclassified_as_figures(nature_manifest):
    figure_ids = {
        o.semantic_id
        for o in nature_manifest.objects
        if o.type is ObjectType.FIGURE
    }

    assert not any(sid and sid.startswith("table:") for sid in figure_ids)


def test_table_objects_carry_region_evidence(nature_manifest):
    tables = [o for o in nature_manifest.objects if o.type is ObjectType.TABLE]

    assert len(tables) == 3
    for table in tables:
        evidence = next(
            e for e in table.detector_evidence if e.detector == "table_rule_lines"
        )
        assert evidence.details["rule_lines"] >= 2
        assert evidence.details["reconstructed"] is False


def test_table_objects_queue_structured_cells(nature_manifest):
    """033i：有区域的表进入单元格翻译队列。"""
    for table in (o for o in nature_manifest.objects if o.type is ObjectType.TABLE):
        assert table.planned_action == "translate_cells"
        assert table.translatable_blocks


def test_exclusion_rects_feed_body_filtering():
    doc = pymupdf.open(NATURE)
    try:
        page = doc[4]
        assert table_exclusion_rects(page)
        unfiltered = len(body_blocks(page))
        filtered = len(body_blocks(page, exclude_rects=figure_table_rects(page)))
    finally:
        doc.close()

    assert filtered < unfiltered


def test_no_regions_without_rule_lines():
    """圈不定就返回空并留给上层记 issue，不猜。"""
    doc = pymupdf.open()
    try:
        page = doc.new_page()
        page.insert_text((72, 100), "Table 1 Something without any rules")
        assert table_regions(page) == []
    finally:
        doc.close()


def test_undelimitable_table_is_recorded_not_silently_dropped(tmp_path):
    """有表题注却圈不定区域时必须留痕，否则表内文字会静默漏进正文。"""
    path = tmp_path / "ruleless.pdf"
    doc = pymupdf.open()
    try:
        page = doc.new_page()
        page.insert_text((72, 100), "Table 1 Outcomes without any rule lines")
        page.insert_text(
            (72, 140),
            "A paragraph of body text long enough to survive the body block filter.",
        )
        doc.save(path)
    finally:
        doc.close()

    manifest = PdfStructureScanner().scan(path)

    assert "TABLE_GEOMETRY_MISSING" in {i.code for i in manifest.issues}


def test_region_tuple_roundtrip():
    region = TableRegion(number=1, x0=1.0, y0=2.0, x1=3.0, y1=4.0, line_count=3)

    assert region.as_tuple() == (1.0, 2.0, 3.0, 4.0)


def test_gap_break_threshold_stays_within_measured_bounds():
    """下界 0.139（ljae439 表头到底线），上界 0.293（Nature 表底到页脚）。"""
    assert 0.139 < ROW_GAP_BREAK_FRAC < 0.293


def test_landscape_frame_table_is_delimited(generated_structure_fixtures: Path):
    path = generated_structure_fixtures / "landscape-frame-table.pdf"
    doc = pymupdf.open(path)
    try:
        regions = table_regions(doc[0])
    finally:
        doc.close()

    assert len(regions) == 1
    region = regions[0]
    assert region.number == 1
    assert region.x0 < 100
    assert region.x1 > 300
    assert region.y1 - region.y0 > 600


def test_landscape_frame_table_has_region_evidence(generated_structure_fixtures: Path):
    path = generated_structure_fixtures / "landscape-frame-table.pdf"
    manifest = PdfStructureScanner().scan(path)
    tables = [o for o in manifest.objects if o.type is ObjectType.TABLE]
    assert len(tables) == 1
    table = tables[0]
    assert table.bbox.x1 - table.bbox.x0 > 200
    assert "TABLE_GEOMETRY_MISSING" not in {i.code for i in manifest.issues}
    evidence = next(e for e in table.detector_evidence if e.detector == "table_rule_lines")
    assert evidence.details["rule_lines"] >= 2


def test_plan033_sample_table_1_has_geometry():
    from tests.structure.sample_paths import PLAN033_SAMPLE_SHA256, plan033_academic_sample

    path = plan033_academic_sample()
    if path is None:
        pytest.skip("PLAN-033 11-page academic PDF is not on this host")
    import hashlib

    if hashlib.sha256(path.read_bytes()).hexdigest() != PLAN033_SAMPLE_SHA256:
        pytest.skip("PLAN-033 sample hash drifted")
    manifest = PdfStructureScanner().scan(path)
    assert "TABLE_GEOMETRY_MISSING" not in {i.code for i in manifest.issues}
    tables = {o.semantic_id: o for o in manifest.objects if o.type is ObjectType.TABLE}
    assert set(tables) == {"table:1", "table:2", "table:3", "table:4"}
    for table in tables.values():
        evidence = next(
            (e for e in table.detector_evidence if e.detector == "table_rule_lines"),
            None,
        )
        assert evidence is not None, table.semantic_id
        assert table.bbox.x1 - table.bbox.x0 > 20
        assert table.bbox.y1 - table.bbox.y0 > 20
