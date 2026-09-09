# SPDX-License-Identifier: MPL-2.0
"""PLAN-030d：PDF 版面分析——栏位判定、正文块与阅读顺序。

不接入 BabelDOC DocLayout：其权重未装进本仓 venv，且 CPU 逐页推理约 1s/页，
19 页样本实测 20s，超出 Tier-3 预扫描 25s 预算。此处用 PyMuPDF 文本块几何做
轻量判定（46 页样本约 1s），金样抽页人工核对一致。判定依据见 WT-030d。
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

from .models import LayoutMode
from .references import is_reference_heading

# 正文块下限：短于此长度多为页眉、页码、图注碎片
MIN_BODY_CHARS = 40
# 超过此宽度视为跨栏或整页框；低于则多为竖排水印
MAX_BLOCK_WIDTH_FRAC = 0.95
MIN_BLOCK_WIDTH_FRAC = 0.05
# 窄于此宽度的块才可能属于某一栏
COLUMN_BLOCK_WIDTH_FRAC = 0.62
# 左右两簇中心的最小间距，低于此值视为同一栏的抖动
COLUMN_CENTER_GAP = 0.22
# 宽高比达到此值按幻灯处理；与 pdf_figure_crop.is_slide_page 口径一致
SLIDE_ASPECT = 1.55
# 与 Figure/Table 区域重叠超过此比例的文本块不算正文
MAX_FIGURE_OVERLAP = 0.20


@dataclass(frozen=True)
class TextBlock:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2.0


def looks_tabular(text: str) -> bool:
    """数字密集的多行短文本：表格数据行。

    PyMuPDF find_tables() 并非总能框住表格（无竖线的三线表常整个测不到），
    此时表格行会被当成正文块。按内容形态兜底识别。
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    if statistics.mean(len(line) for line in lines) > 24:
        return False
    digits = sum(c.isdigit() for c in text)
    letters = sum(c.isalpha() for c in text)
    return digits > letters


def _overlap_frac(block: TextBlock, rect) -> float:
    area = (block.x1 - block.x0) * (block.y1 - block.y0)
    if area <= 0:
        return 0.0
    ix0 = max(block.x0, float(rect.x0))
    iy0 = max(block.y0, float(rect.y0))
    ix1 = min(block.x1, float(rect.x1))
    iy1 = min(block.y1, float(rect.y1))
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    return ((ix1 - ix0) * (iy1 - iy0)) / area


def body_blocks(
    page, exclude_rects=None, *, raw_blocks: list | None = None
) -> list[TextBlock]:
    """页面上可作为正文候选的文本块。

    落在 Figure/Table 区域内的文字（如流程图节点、表格单元格）不是正文，必须排除，
    否则会被当成跨栏正文并污染阅读顺序。
    """
    width = float(page.rect.width)
    if width <= 0:
        return []
    excluded = list(exclude_rects or [])
    out: list[TextBlock] = []
    source_blocks = page.get_text("blocks") if raw_blocks is None else raw_blocks
    for raw in source_blocks:
        x0, y0, x1, y1, text = raw[0], raw[1], raw[2], raw[3], raw[4]
        if len(str(text).strip()) < MIN_BODY_CHARS and not is_reference_heading(str(text)):
            continue
        frac = (x1 - x0) / width
        if frac < MIN_BLOCK_WIDTH_FRAC or frac > MAX_BLOCK_WIDTH_FRAC:
            continue
        if looks_tabular(str(text)):
            continue
        block = TextBlock(float(x0), float(y0), float(x1), float(y1), str(text))
        if any(_overlap_frac(block, r) > MAX_FIGURE_OVERLAP for r in excluded):
            continue
        out.append(block)
    return out


def figure_table_rects(page) -> list:
    """该页的 Figure/Table 区域，用于把图内、表内文字排除出正文。"""
    import sys
    from pathlib import Path

    scripts = Path(__file__).resolve().parents[2] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from .captions import caption_anchors
    from .tables import table_exclusion_rects

    try:
        from pdf_figure_crop import (
            labeled_figure_regions,
            page_caption_profile,
            translatable_regions,
        )
    except ImportError:
        return list(table_exclusion_rects(page))
    anchors = caption_anchors(page)
    profile = page_caption_profile(page, anchors=anchors)
    try:
        drawings = page.get_drawings() or []
    except Exception:
        drawings = []
    try:
        raw_blocks = page.get_text("blocks") or []
    except Exception:
        raw_blocks = []
    rects = list(
        table_exclusion_rects(page, anchors=anchors, drawings=drawings)
    )
    labeled = labeled_figure_regions(
        page,
        profile=profile,
        tables=rects,
        drawings=drawings,
        text_blocks=raw_blocks,
    )
    rects.extend(labeled.values())
    if not labeled:
        rects.extend(
            translatable_regions(
                page,
                profile=profile,
                tables=rects,
                drawings=drawings,
                text_blocks=raw_blocks,
            )
        )
    return rects


def detect_layout_mode(page, blocks: list[TextBlock] | None = None) -> LayoutMode:
    """判定页面栏式。幻灯先行短路，避免把自由版面当成栏式。"""
    width = float(page.rect.width)
    height = float(page.rect.height)
    if height > 0 and width / height >= SLIDE_ASPECT:
        return LayoutMode.FREEFORM
    items = body_blocks(page) if blocks is None else blocks
    if len(items) < 3:
        return LayoutMode.SINGLE
    narrow = [
        b.center_x / width
        for b in items
        if (b.x1 - b.x0) / width < COLUMN_BLOCK_WIDTH_FRAC
    ]
    if len(narrow) < 2:
        return LayoutMode.SINGLE
    left = [c for c in narrow if c < 0.5]
    right = [c for c in narrow if c >= 0.5]
    if not left or not right:
        return LayoutMode.SINGLE
    if statistics.mean(right) - statistics.mean(left) > COLUMN_CENTER_GAP:
        return LayoutMode.DOUBLE
    return LayoutMode.SINGLE


def column_count(mode: LayoutMode) -> int | None:
    return {LayoutMode.SINGLE: 1, LayoutMode.DOUBLE: 2}.get(mode)


def reading_order(page, mode: LayoutMode, blocks: list[TextBlock] | None = None) -> list[TextBlock]:
    """按阅读顺序排列正文块。

    双栏按「左栏自上而下 → 右栏自上而下」；其余按自上而下、同高再自左而右。
    """
    items = body_blocks(page) if blocks is None else list(blocks)
    if not items:
        return []
    if mode is not LayoutMode.DOUBLE:
        return sorted(items, key=lambda b: (round(b.y0, 1), b.x0))
    width = float(page.rect.width)
    left = [b for b in items if b.center_x / width < 0.5]
    right = [b for b in items if b.center_x / width >= 0.5]
    key = lambda b: (round(b.y0, 1), b.x0)  # noqa: E731
    return sorted(left, key=key) + sorted(right, key=key)


def column_of(block: TextBlock, page, mode: LayoutMode) -> str:
    """块的栏归属：left / right / full / single。

    双栏页上的标题、图题、表格标题本来就横跨两栏，属于合法的 full 元素，不是
    跨栏串接缺陷；把它们标出来而不是报警，执行阶段才能据此判断译文能否膨胀。
    """
    if mode is not LayoutMode.DOUBLE:
        return "single"
    width = float(page.rect.width)
    if width <= 0:
        return "single"
    if (block.x1 - block.x0) / width >= COLUMN_BLOCK_WIDTH_FRAC:
        return "full"
    return "left" if block.center_x / width < 0.5 else "right"


def overflows_column(block: TextBlock, page, mode: LayoutMode) -> bool:
    """窄块越过栏中线——正文栏内文字不应如此，属于真正的跨栏串接。"""
    if mode is not LayoutMode.DOUBLE:
        return False
    width = float(page.rect.width)
    if width <= 0:
        return False
    if (block.x1 - block.x0) / width >= COLUMN_BLOCK_WIDTH_FRAC:
        return False
    return block.x0 / width < 0.5 < block.x1 / width
