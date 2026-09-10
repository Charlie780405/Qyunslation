# SPDX-License-Identifier: MPL-2.0
"""PLAN-030d Task 8：表格区域检测与保护。

不用 PyMuPDF `find_tables()`：实测在临床期刊的无竖线三线表上召回率 2/6，唯一
命中的那个列数也是错的，且在图表页产生大量空表假阳性；`strategy="text"` 会把
整页当表格并将文字拦腰切断，足以破坏临床数值。改从表题注锚点出发，按横线群
圈定区域——只求可靠圈定并保护，不做单元格重建。完整探底数据见 WT-030d。
"""
from __future__ import annotations

from dataclasses import dataclass

# 同一条横线被切成多段时的 y 合并容差（pt）
LINE_MERGE_TOL = 1.5
# 线段至少要有这么宽才算表格横线，滤掉下划线、短装饰
MIN_LINE_WIDTH_FRAC = 0.10
# 相邻横线间距超过页高这个比例即认为表格结束，用于甩掉页脚线。
# 金样实测下界 0.139（表头线到底线），上界 0.293（表格底到页脚线）。见 WT-030d。
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


def _horizontal_lines(
    page, *, drawings: list | None = None
) -> list[tuple[float, float, float]]:
    """页面横线，返回 (x0, x1, y)，已按 y 合并同一条线的分段。"""
    width = float(page.rect.width)
    if width <= 0:
        return []
    raw: list[tuple[float, float, float]] = []
    if drawings is None:
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


def _vertical_lines(
    page, *, drawings: list | None = None
) -> list[tuple[float, float, float]]:
    """页面竖线，返回 (y0, y1, x)，已按 x 合并同一条线的分段。"""
    height = float(page.rect.height)
    if height <= 0:
        return []
    raw: list[tuple[float, float, float]] = []
    if drawings is None:
        try:
            drawings = page.get_drawings()
        except Exception:
            return []
    for drawing in drawings:
        for item in drawing.get("items", []):
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                if abs(p1.x - p2.x) > 1.0:
                    continue
                y0, y1, x = min(p1.y, p2.y), max(p1.y, p2.y), (p1.x + p2.x) / 2
            elif item[0] == "re":
                rect = item[1]
                if rect.width > 2.0:
                    continue
                y0, y1, x = rect.y0, rect.y1, (rect.x0 + rect.x1) / 2
            else:
                continue
            if (y1 - y0) / height < MIN_LINE_WIDTH_FRAC:
                continue
            raw.append((float(y0), float(y1), float(x)))

    merged: list[list[float]] = []
    for y0, y1, x in sorted(raw, key=lambda t: t[2]):
        if merged and abs(x - merged[-1][2]) <= LINE_MERGE_TOL:
            merged[-1][0] = min(merged[-1][0], y0)
            merged[-1][1] = max(merged[-1][1], y1)
        else:
            merged.append([y0, y1, x])
    return [(m[0], m[1], m[2]) for m in merged]


def _frame_near_caption(
    h_lines: list[tuple[float, float, float]],
    v_lines: list[tuple[float, float, float]],
    caption_bbox: tuple[float, float, float, float],
    caption_gap: float,
) -> tuple[float, float, float, float, int] | None:
    """侧放/整页框线表：两横 + 两竖围成矩形，且与题注相邻。"""
    if len(h_lines) < 2 or len(v_lines) < 2:
        return None
    cx0, cy0, cx1, cy1 = (float(v) for v in caption_bbox)
    best: tuple[float, float, float, float, int] | None = None
    best_area = 0.0
    for i, (hx0_a, hx1_a, hy_a) in enumerate(h_lines):
        for hx0_b, hx1_b, hy_b in h_lines[i + 1 :]:
            y0, y1 = (hy_a, hy_b) if hy_a <= hy_b else (hy_b, hy_a)
            if y1 - y0 < 24.0:
                continue
            ox0, ox1 = max(hx0_a, hx0_b), min(hx1_a, hx1_b)
            if ox1 - ox0 < 24.0:
                continue
            lefts = [
                x
                for vy0, vy1, x in v_lines
                if abs(x - ox0) <= 8.0 and vy0 <= y0 + 8.0 and vy1 >= y1 - 8.0
            ]
            rights = [
                x
                for vy0, vy1, x in v_lines
                if abs(x - ox1) <= 8.0 and vy0 <= y0 + 8.0 and vy1 >= y1 - 8.0
            ]
            if not lefts or not rights:
                continue
            fx0, fx1 = min(lefts), max(rights)
            if fx1 - fx0 < 24.0:
                continue
            if not _caption_touches_frame((cx0, cy0, cx1, cy1), (fx0, y0, fx1, y1), caption_gap):
                continue
            area = (fx1 - fx0) * (y1 - y0)
            if area > best_area:
                best_area = area
                best = (fx0, y0, fx1, y1, 4)
    return best


def _caption_touches_frame(
    caption: tuple[float, float, float, float],
    frame: tuple[float, float, float, float],
    gap: float,
) -> bool:
    cx0, cy0, cx1, cy1 = caption
    fx0, fy0, fx1, fy1 = frame
    y_overlap = min(cy1, fy1) - max(cy0, fy0)
    x_overlap = min(cx1, fx1) - max(cx0, fx0)
    left = cx1 <= fx0 + 2.0 and (fx0 - cx1) <= gap and y_overlap > 0
    right = fx1 <= cx0 + 2.0 and (cx0 - fx1) <= gap and y_overlap > 0
    above = cy1 <= fy0 + 2.0 and (fy0 - cy1) <= gap and x_overlap > 0
    below = fy1 <= cy0 + 2.0 and (cy0 - fy1) <= gap and x_overlap > 0
    inside = x_overlap > 0 and y_overlap > 0
    return left or right or above or below or inside


def picture_table_region(page, caption_bbox, number: int) -> TableRegion | None:
    """题注下方最大位图块 → 纯图片表区域。无合适位图则 None（fail-closed）。"""
    try:
        blocks = page.get_text("dict").get("blocks", []) or []
    except Exception:
        return None
    try:
        page_w = float(page.rect.width)
        page_h = float(page.rect.height)
    except Exception:
        return None
    if page_w <= 0 or page_h <= 0:
        return None
    caption_bottom = float(caption_bbox[3])
    best: tuple[float, float, float, float] | None = None
    best_area = 0.0
    min_area = page_w * page_h * 0.02
    max_gap = page_h * 0.35
    for block in blocks:
        if block.get("type") != 1:
            continue
        bbox = block.get("bbox")
        if not bbox or len(bbox) < 4:
            continue
        x0, y0, x1, y1 = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
        if y1 <= caption_bottom + 1.0:
            continue
        if y0 - caption_bottom > max_gap:
            continue
        area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
        if area < min_area:
            continue
        if area > best_area:
            best_area = area
            best = (x0, y0, x1, y1)
    if best is None:
        return None
    x0, y0, x1, y1 = best
    return TableRegion(
        number=int(number),
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
        line_count=0,
    )


def table_regions(
    page, anchors=None, *, drawings: list | None = None
) -> list[TableRegion]:
    """由表题注锚点圈定的表格区域。

    无表题注的页返回空列表——这是不产生假阳性的关键：图表页的线框再多也不会
    被当成表格。PLAN-033b：题注下方横线群失败时，再用封闭框线回退。
    PLAN-038d：无线条时回退题注下方最大位图（纯图片表）。
    """
    from .captions import caption_anchors

    height = float(page.rect.height)
    if height <= 0:
        return []
    anchors = caption_anchors(page) if anchors is None else anchors
    captions = [a for a in anchors if a[0] == "table"]
    if not captions:
        return []
    if drawings is None:
        try:
            drawings = page.get_drawings()
        except Exception:
            drawings = []
    lines = _horizontal_lines(page, drawings=drawings)
    v_lines = _vertical_lines(page, drawings=drawings)
    regions: list[TableRegion] = []
    taken: set[int] = set()

    if lines or v_lines:
        gap_break = height * ROW_GAP_BREAK_FRAC
        caption_gap = height * CAPTION_TO_TABLE_FRAC
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
            if len(group) >= 2:
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
                taken.add(number)
                continue
            frame = _frame_near_caption(lines, v_lines, bbox, caption_gap)
            if frame is None or number in taken:
                continue
            fx0, fy0, fx1, fy1, nlines = frame
            regions.append(
                TableRegion(
                    number=number,
                    x0=fx0,
                    y0=fy0,
                    x1=fx1,
                    y1=fy1,
                    line_count=nlines,
                )
            )
            taken.add(number)

    for _, number, _, bbox in captions:
        if number in taken:
            continue
        pic = picture_table_region(page, bbox, number)
        if pic is not None:
            regions.append(pic)
            taken.add(number)
    return regions


def table_exclusion_rects(
    page, anchors=None, *, drawings: list | None = None
) -> list:
    """供正文过滤使用的表格矩形，含题注到底线的整块区域。"""
    import pymupdf

    out = []
    for region in table_regions(page, anchors=anchors, drawings=drawings):
        out.append(pymupdf.Rect(region.x0, region.y0, region.x1, region.y1))
    return out
