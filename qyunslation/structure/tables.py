# SPDX-License-Identifier: MPL-2.0
"""PLAN-030d Task 8：表格区域检测与保护。

不用 PyMuPDF `find_tables()`：实测在临床期刊的无竖线三线表上召回率 2/6，唯一
命中的 Nature p4 列数也是错的，且在图表页产生大量空表假阳性；`strategy="text"`
会把整页当表格并将文字拦腰切断，足以破坏临床数值。改从表题注锚点出发，按横线
群圈定区域——只求可靠圈定并保护，不做单元格重建。依据见 WT-030d。
"""
from __future__ import annotations

from dataclasses import dataclass

# 同一条横线被切成多段时的 y 合并容差（pt）
LINE_MERGE_TOL = 1.5
# 线段至少要有这么宽才算表格横线，滤掉下划线、短装饰
MIN_LINE_WIDTH_FRAC = 0.10
# 相邻横线间距超过页高这个比例即认为表格结束，用于甩掉页脚线。
# 下界受 ljae439 p5 约束（表头线 0.148 到底线 0.287 相隔 0.139），
# 上界受 Nature p5 约束（表格底 0.661 到页脚线 0.954 相隔 0.293）。
ROW_GAP_BREAK_FRAC = 0.20
# 题注与表格顶线之间允许的最大间隔
CAPTION_TO_TABLE_FRAC = 0.06


@dataclass(frozen=True)
class TableRegion:
    number: int
    x0: float
    y0: float
    x1: float
    y1: float
    line_count: int

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)


def _horizontal_lines(page) -> list[tuple[float, float, float]]:
    """页面横线，返回 (x0, x1, y)，已按 y 合并同一条线的分段。"""
    width = float(page.rect.width)
    if width <= 0:
        return []
    raw: list[tuple[float, float, float]] = []
    try:
        drawings = page.get_drawings()
    except Exception:
        return []
    for drawing in drawings:
        for item in drawing.get("items", []):
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) > 1.0:
                    continue
                x0, x1, y = min(p1.x, p2.x), max(p1.x, p2.x), (p1.y + p2.y) / 2
            elif item[0] == "re":
                rect = item[1]
                if rect.height > 2.0:
                    continue
                x0, x1, y = rect.x0, rect.x1, rect.y0
            else:
                continue
            if (x1 - x0) / width < MIN_LINE_WIDTH_FRAC:
                continue
            raw.append((float(x0), float(x1), float(y)))

    merged: list[list[float]] = []
    for x0, x1, y in sorted(raw, key=lambda t: t[2]):
        if merged and abs(y - merged[-1][2]) <= LINE_MERGE_TOL:
            merged[-1][0] = min(merged[-1][0], x0)
            merged[-1][1] = max(merged[-1][1], x1)
        else:
            merged.append([x0, x1, y])
    return [(m[0], m[1], m[2]) for m in merged]


def table_regions(page, anchors=None) -> list[TableRegion]:
    """由表题注锚点圈定的表格区域。

    无表题注的页返回空列表——这是不产生假阳性的关键：图表页的线框再多也不会
    被当成表格。
    """
    from .captions import caption_anchors

    height = float(page.rect.height)
    if height <= 0:
        return []
    anchors = caption_anchors(page) if anchors is None else anchors
    captions = [a for a in anchors if a[0] == "table"]
    if not captions:
        return []
    lines = _horizontal_lines(page)
    if not lines:
        return []

    gap_break = height * ROW_GAP_BREAK_FRAC
    caption_gap = height * CAPTION_TO_TABLE_FRAC
    regions: list[TableRegion] = []
    consumed: set[int] = set()

    for _, number, _, bbox in captions:
        caption_bottom = float(bbox[3])
        group: list[tuple[float, float, float]] = []
        for index, (x0, x1, y) in enumerate(lines):
            if index in consumed or y < caption_bottom:
                continue
            if not group:
                if y - caption_bottom > caption_gap:
                    break
                group.append((x0, x1, y))
                consumed.add(index)
                continue
            if y - group[-1][2] > gap_break:
                break
            group.append((x0, x1, y))
            consumed.add(index)
        if len(group) < 2:
            continue
        regions.append(
            TableRegion(
                number=number,
                x0=min(g[0] for g in group),
                y0=group[0][2],
                x1=max(g[1] for g in group),
                y1=group[-1][2],
                line_count=len(group),
            )
        )
    return regions


def table_exclusion_rects(page, anchors=None) -> list:
    """供正文过滤使用的表格矩形，含题注到底线的整块区域。"""
    import pymupdf

    out = []
    for region in table_regions(page, anchors=anchors):
        out.append(pymupdf.Rect(region.x0, region.y0, region.x1, region.y1))
    return out
