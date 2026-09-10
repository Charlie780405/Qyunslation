"""PLAN-030h H4：多栏 / 混合栏 / 自由布局 / 海报分区的版式金样。

`LayoutMode` 声明了 SINGLE/DOUBLE/MULTI/MIXED/FREEFORM 五种栏式，
`profiles.py` 也把 MULTI 写进 RESEARCH_ARTICLE 的 expected_layout_modes，
但此前没有任何夹具产出三栏及以上、逐页混合栏或海报分区的版面——契约声明
的能力从未被真实版面检验过。

这些金样把当前行为钉死。其中几条锁的是**缺陷**而非正确行为，每条都在
docstring 里写清了它锁的是什么、后果是什么。修好实现时这些断言会转红，
那正是提醒摘掉它们的时机。
"""
from __future__ import annotations

import pymupdf
import pytest

from qyunslation.structure.layout import (
    SLIDE_ASPECT,
    body_blocks,
    column_of,
    detect_layout_mode,
    reading_order,
)
from qyunslation.structure.models import LayoutMode


def _page(generated_structure_fixtures, name: str, index: int = 0):
    document = pymupdf.open(generated_structure_fixtures / name)
    try:
        yield document[index]
    finally:
        document.close()


@pytest.fixture
def three_column(generated_structure_fixtures):
    yield from _page(generated_structure_fixtures, "three-column.pdf")


@pytest.fixture
def four_column(generated_structure_fixtures):
    yield from _page(generated_structure_fixtures, "four-column.pdf")


@pytest.fixture
def poster(generated_structure_fixtures):
    yield from _page(generated_structure_fixtures, "poster-sections.pdf")


def test_multi_column_mode_is_produced_for_three_and_four_columns(
    three_column, four_column
):
    """030j D1：三栏与四栏产出 MULTI，不再一律压成 DOUBLE。"""
    assert detect_layout_mode(three_column) is LayoutMode.MULTI
    assert detect_layout_mode(four_column) is LayoutMode.MULTI


def test_middle_column_gets_middle_label_in_multi_layout(three_column):
    """030j D2：三栏中栏标 middle，不再按中线二分归左/右。"""
    mode = detect_layout_mode(three_column)
    width = float(three_column.rect.width)
    blocks = body_blocks(three_column)

    assert mode is LayoutMode.MULTI
    middle_blocks = [b for b in blocks if 0.33 < b.center_x / width < 0.67]
    assert middle_blocks
    for block in middle_blocks:
        assert column_of(block, three_column, mode) == "middle"


def test_two_column_page_with_few_blocks_is_double(
    generated_structure_fixtures,
):
    """030j D3：仅两块正文的双栏页仍判 DOUBLE，不短路 SINGLE。"""
    document = pymupdf.open(generated_structure_fixtures / "mixed-columns.pdf")
    try:
        page = document[1]
        assert len(body_blocks(page)) == 2
        assert detect_layout_mode(page) is LayoutMode.DOUBLE
    finally:
        document.close()


def test_mixed_document_resolves_layout_per_page(generated_structure_fixtures):
    """混合栏文档逐页判定，文档级不存在 MIXED 这一档。

    canvas.layout_mode 是页级属性，「混合」只能是各页栏式不同这一观察结果。
    """
    document = pymupdf.open(generated_structure_fixtures / "mixed-columns.pdf")
    try:
        modes = [detect_layout_mode(page) for page in document]
    finally:
        document.close()

    assert len(modes) == 3
    assert modes[0] is LayoutMode.SINGLE  # 通栏扉页
    assert modes[2] is LayoutMode.MULTI  # 三栏附录
    assert LayoutMode.MIXED not in modes


def test_poster_is_recognised_as_freeform(poster):
    """030j D4：A0 横版海报（宽高比 ~1.41）须走 FREEFORM，不得误判 DOUBLE。"""
    aspect = float(poster.rect.width) / float(poster.rect.height)

    assert aspect == pytest.approx(1.41, abs=0.01)
    assert aspect < SLIDE_ASPECT
    assert aspect >= 1.38
    assert detect_layout_mode(poster) is LayoutMode.FREEFORM


def test_poster_panels_keep_spatial_reading_order(poster):
    """FREEFORM 下九分区按 y→x 排序，不再被中线劈成两串。"""
    mode = detect_layout_mode(poster)
    blocks = body_blocks(poster)
    ordered = reading_order(poster, mode)

    assert mode is LayoutMode.FREEFORM
    assert len(blocks) == 9
    assert ordered == sorted(blocks, key=lambda b: (round(b.y0, 1), b.x0))
    assert ordered[0].y0 < ordered[-1].y0


def test_slide_aspect_short_circuit_still_guards_real_slides(
    generated_structure_fixtures,
):
    """对照组：16:9 幻灯确实走了自由版面短路，说明短路本身是好的，
    问题只在海报的宽高比够不着这条线。"""
    document = pymupdf.open(generated_structure_fixtures / "slide-equivalent.pdf")
    try:
        page = document[0]
        aspect = float(page.rect.width) / float(page.rect.height)
        assert aspect >= SLIDE_ASPECT
        assert detect_layout_mode(page) is LayoutMode.FREEFORM
    finally:
        document.close()
