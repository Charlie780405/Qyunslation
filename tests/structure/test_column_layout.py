"""PLAN-030d Tasks 6–7：正文 BODY 对象、栏式判定与阅读顺序。"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pymupdf
import pytest

from qyunslation.structure import PdfStructureScanner
from qyunslation.structure.ingest import prepare_document
from qyunslation.structure.layout import (
    TextBlock,
    body_blocks,
    column_of,
    detect_layout_mode,
    looks_tabular,
    overflows_column,
    reading_order,
)
from qyunslation.structure.models import ExecutionStatus, LayoutMode, ObjectType

ROOT = Path(__file__).resolve().parents[2]
from tests.structure.sample_paths import slide_sample

LJAE = ROOT / "tests/fixtures/structure/reference/ljae439.pdf"
NATURE = ROOT / "tests/fixtures/structure/reference/nature_comm_53384.pdf"
SLIDE = slide_sample()

requires_slide = pytest.mark.skipif(
    not SLIDE.is_file(), reason="slide sample lives outside the repo"
)


@pytest.fixture(scope="module")
def ljae():
    return PdfStructureScanner().scan(LJAE)


@pytest.fixture(scope="module")
def nature():
    return PdfStructureScanner().scan(NATURE)


def _bodies(manifest):
    return [o for o in manifest.objects if o.type is ObjectType.BODY]


def _modes(path: Path):
    prep = prepare_document(path.name, path.read_bytes(), declared_mime="application/pdf")
    return [c.layout_mode for c in prep.canvases]


def test_canvas_layout_mode_is_no_longer_hardcoded_mixed():
    modes = _modes(NATURE)

    assert LayoutMode.MIXED not in modes
    assert LayoutMode.DOUBLE in modes


def test_journal_pages_are_mostly_double_column():
    counts = Counter(_modes(NATURE))

    assert counts[LayoutMode.DOUBLE] == 18
    assert counts[LayoutMode.SINGLE] == 1


def test_full_width_front_matter_is_single_column():
    """ljae439 前两页是全宽标题页与 Plain Language Summary。"""
    modes = _modes(LJAE)

    assert modes[0] is LayoutMode.SINGLE
    assert modes[1] is LayoutMode.SINGLE
    assert Counter(modes)[LayoutMode.DOUBLE] == 8


@requires_slide
def test_slides_are_freeform_not_columnar():
    modes = _modes(SLIDE)

    assert set(modes) == {LayoutMode.FREEFORM}


def test_body_objects_are_produced_with_reading_order(nature):
    bodies = _bodies(nature)

    assert bodies
    for canvas in nature.canvases:
        orders = [
            o.reading_order for o in bodies if o.canvas_id == canvas.canvas_id
        ]
        if not orders:
            continue
        assert orders == list(range(len(orders)))


def test_canvas_reading_order_lists_body_objects(nature):
    by_id = {o.object_id: o for o in _bodies(nature)}

    for canvas in nature.canvases:
        for object_id in canvas.reading_order:
            assert object_id in by_id


def test_double_column_reading_order_is_left_then_right(nature):
    bodies = {o.object_id: o for o in _bodies(nature)}

    for canvas in nature.canvases:
        if canvas.layout_mode is not LayoutMode.DOUBLE:
            continue
        columns = [
            bodies[oid].detector_evidence[0].details["column"]
            for oid in canvas.reading_order
        ]
        left_positions = [i for i, c in enumerate(columns) if c == "left"]
        right_positions = [i for i, c in enumerate(columns) if c == "right"]
        if left_positions and right_positions:
            assert max(left_positions) < min(right_positions)


def test_body_is_delegated_to_babeldoc_not_claimed(nature):
    for body in _bodies(nature):
        assert body.execution_status is ExecutionStatus.EXPLICITLY_SKIPPED
        assert body.reason_code == "delegated_to_babeldoc"
        assert body.planned_action == "babeldoc_text_layer"


def test_body_blocks_exclude_figure_and_table_regions():
    """CONSORT 流程图内的文字不是正文。"""
    doc = pymupdf.open(NATURE)
    try:
        page = doc[2]
        from qyunslation.structure.layout import figure_table_rects

        unfiltered = len(body_blocks(page))
        filtered = len(body_blocks(page, exclude_rects=figure_table_rects(page)))
    finally:
        doc.close()

    assert filtered < unfiltered


def test_column_overflow_is_limited_to_front_matter(nature):
    overflows = [i for i in nature.issues if i.code == "LAYOUT_COLUMN_OVERFLOW"]

    assert all(i.details["page"] == 1 for i in overflows)


def test_ljae_has_no_column_overflow(ljae):
    assert [i for i in ljae.issues if i.code == "LAYOUT_COLUMN_OVERFLOW"] == []


def test_tabular_rows_are_not_treated_as_body():
    assert looks_tabular("0\n0\n1 (6.3)\n1 (5.9)\n2 (5.9)\n0\n2 (9.5)")
    assert not looks_tabular(
        "Regulatory T cell impairment is implicated in the pathogenesis of "
        "many inflammatory diseases and restoring homeostasis may help."
    )


def test_column_attribution_labels():
    page = pymupdf.open(NATURE)[2]
    width = page.rect.width

    left = TextBlock(0.07 * width, 10, 0.49 * width, 40, "x")
    right = TextBlock(0.51 * width, 10, 0.94 * width, 40, "x")
    full = TextBlock(0.07 * width, 10, 0.94 * width, 40, "x")

    assert column_of(left, page, LayoutMode.DOUBLE) == "left"
    assert column_of(right, page, LayoutMode.DOUBLE) == "right"
    assert column_of(full, page, LayoutMode.DOUBLE) == "full"
    assert column_of(left, page, LayoutMode.SINGLE) == "single"


def test_full_width_titles_are_not_flagged_as_overflow():
    """双栏页上的标题、图题本来就跨栏，不是缺陷。"""
    page = pymupdf.open(NATURE)[3]
    width = page.rect.width
    title = TextBlock(0.07 * width, 10, 0.94 * width, 40, "Table 1 | Demographics")

    assert overflows_column(title, page, LayoutMode.DOUBLE) is False


def test_narrow_block_crossing_the_midline_is_flagged():
    page = pymupdf.open(NATURE)[3]
    width = page.rect.width
    strays = TextBlock(0.40 * width, 10, 0.60 * width, 40, "stray")

    assert overflows_column(strays, page, LayoutMode.DOUBLE) is True


def test_single_column_pages_never_report_overflow():
    page = pymupdf.open(LJAE)[1]
    width = page.rect.width
    block = TextBlock(0.10 * width, 10, 0.90 * width, 40, "x")

    assert overflows_column(block, page, LayoutMode.SINGLE) is False


def test_reading_order_is_top_down_for_single_column():
    doc = pymupdf.open(LJAE)
    try:
        page = doc[1]
        ordered = reading_order(page, LayoutMode.SINGLE)
    finally:
        doc.close()

    tops = [b.y0 for b in ordered]
    assert tops == sorted(tops)


def test_detect_layout_mode_is_stable_across_calls():
    doc = pymupdf.open(NATURE)
    try:
        first = [detect_layout_mode(p) for p in doc]
        second = [detect_layout_mode(p) for p in doc]
    finally:
        doc.close()

    assert first == second
