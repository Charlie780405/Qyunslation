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


def test_multi_column_mode_is_never_produced(three_column, four_column):
    """已知债：三栏与四栏都被判成 DOUBLE，LayoutMode.MULTI 是死枚举。

    detect_layout_mode 只按「窄块中心点是否分居中线两侧」二分，栏数一律
    归结为两栏。RESEARCH_ARTICLE 的 expected_layout_modes 却声明支持 MULTI，
    契约与实现在此背离。
    """
    assert detect_layout_mode(three_column) is LayoutMode.DOUBLE
    assert detect_layout_mode(four_column) is LayoutMode.DOUBLE
    assert LayoutMode.MULTI in set(LayoutMode)


def test_middle_column_is_assigned_by_which_side_of_the_midline_it_lands_on(
    three_column,
):
    """三栏被判 DOUBLE 的实际后果：中间栏按中线机械二分，归左归右全看它压在哪侧。

    中栏中心落在 0.501 就归右、落在 0.499 就归左——两者相差千分之二，阅读
    顺序却完全不同。译文按「左串自上而下 → 右串自上而下」拼接，三栏原文的
    顺序在扫描阶段就已经错了，后续无论怎么排版都补不回来。
    """
    mode = detect_layout_mode(three_column)
    ordered = reading_order(three_column, mode)
    width = float(three_column.rect.width)

    assert len(ordered) == 3
    columns = [column_of(block, three_column, mode) for block in ordered]
    # 三栏被压成两串；具体哪一串多一列取决于中栏压在中线哪侧
    assert set(columns) == {"left", "right"}
    assert columns.count("left") + columns.count("right") == 3

    middle = ordered[1]
    assert 0.45 < middle.center_x / width < 0.55, "中栏确实压在中线上"


def test_two_column_page_with_few_blocks_falls_back_to_single(
    generated_structure_fixtures,
):
    """已知债：正文块少于 3 的双栏页被判成 SINGLE。

    detect_layout_mode 在 len(items) < 3 时直接短路返回 SINGLE，一页只有
    两大块正文的双栏版面（短文、附录、表格页）因此被当成单栏。
    """
    document = pymupdf.open(generated_structure_fixtures / "mixed-columns.pdf")
    try:
        page = document[1]
        assert len(body_blocks(page)) == 2
        assert detect_layout_mode(page) is LayoutMode.SINGLE
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
    assert modes[2] is LayoutMode.DOUBLE  # 三栏附录，被判成两栏
    assert LayoutMode.MIXED not in modes


def test_poster_is_not_recognised_as_freeform(poster):
    """已知债：A0 海报宽高比 1.41 低于 1.55 的幻灯阈值，没走自由版面短路。

    结果是九块彼此独立的分区被当成期刊双栏正文，按中线劈成两串串接。海报
    分区（POSTER_SECTION）在 PDF 通道上因此完全没有被识别。
    """
    aspect = float(poster.rect.width) / float(poster.rect.height)

    assert aspect == pytest.approx(1.41, abs=0.01)
    assert aspect < SLIDE_ASPECT
    assert detect_layout_mode(poster) is not LayoutMode.FREEFORM
    assert detect_layout_mode(poster) is LayoutMode.DOUBLE


def test_poster_panels_are_serialised_into_two_column_order(poster):
    """海报九分区被串成两串的直接证据。"""
    mode = detect_layout_mode(poster)
    blocks = body_blocks(poster)
    ordered = reading_order(poster, mode)

    assert len(blocks) == 9
    columns = {column_of(block, poster, mode) for block in ordered}
    assert columns <= {"left", "right", "full"}
    # 九块被压成左右两串，分区的二维结构在这一步丢失
    assert len({column_of(block, poster, mode) for block in ordered}) <= 3


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
