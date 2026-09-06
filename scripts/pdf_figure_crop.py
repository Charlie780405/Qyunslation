# SPDX-License-Identifier: MPL-2.0
"""PLAN-027d：PDF 矢量图安全聚类（去整页回退，Fail-Closed）。"""
from __future__ import annotations

import os
from typing import Iterable

try:
    import pymupdf
except ImportError:  # pragma: no cover
    pymupdf = None  # type: ignore

MAX_AREA_FRAC = float(os.environ.get("QYUNSLATION_VECTOR_MAX_AREA_FRAC", "0.80"))
TEXT_OVERLAP_MAX = float(os.environ.get("QYUNSLATION_VECTOR_TEXT_OVERLAP", "0.10"))
MIN_DRAWINGS = int(os.environ.get("QYUNSLATION_VECTOR_MIN_DRAWINGS", "8"))
VECTOR_CROP_DPI = int(os.environ.get("QYUNSLATION_VECTOR_CROP_DPI", "300"))
VECTOR_MAX_PX = int(os.environ.get("QYUNSLATION_VECTOR_MAX_PX", "4000"))


def _union_rects(rects: list) -> object | None:
    if not rects:
        return None
    u = pymupdf.Rect(rects[0])
    for r in rects[1:]:
        u |= pymupdf.Rect(r)
    return u


def _long_text_rects(page) -> list:
    """长段落文字块（>60 字符）用于防触碰。"""
    out = []
    try:
        blocks = page.get_text("blocks") or []
    except Exception:
        return out
    for b in blocks:
        if len(b) < 5:
            continue
        text = (b[4] or "").strip()
        if len(text) > 60:
            out.append(pymupdf.Rect(b[0], b[1], b[2], b[3]))
    return out


def _table_rects(page) -> list:
    out = []
    try:
        finder = page.find_tables()
        tables = getattr(finder, "tables", None) or []
        for t in tables:
            bbox = getattr(t, "bbox", None)
            if bbox:
                out.append(pymupdf.Rect(bbox))
    except Exception:
        pass
    return out


def _overlap_ratio(a, b) -> float:
    inter = pymupdf.Rect(a) & pymupdf.Rect(b)
    if inter.is_empty:
        return 0.0
    area_a = abs(a.width * a.height) or 1.0
    return abs(inter.width * inter.height) / area_a


def find_safe_vector_figures(page, exclude_rects: Iterable | None = None) -> list:
    """定位可安全栅格化覆盖的矢量设计图区域。不确定则返回空（Fail-Closed）。"""
    if pymupdf is None:
        return []
    exclude = [pymupdf.Rect(r) for r in (exclude_rects or [])]
    try:
        drawings = page.get_drawings() or []
    except Exception:
        return []
    if len(drawings) < MIN_DRAWINGS:
        return []

    # 收集 drawing rects，去掉与已处理位图大幅重叠的
    rects = []
    for d in drawings:
        r = d.get("rect")
        if not r:
            continue
        rr = pymupdf.Rect(r)
        if rr.is_empty or rr.width < 8 or rr.height < 8:
            continue
        skip = False
        for ex in exclude:
            if _overlap_ratio(rr, ex) > 0.45:
                skip = True
                break
        if not skip:
            rects.append(rr)
    if len(rects) < MIN_DRAWINGS:
        return []

    # 简单聚类：按纵向邻近合并
    rects = sorted(rects, key=lambda r: (r.y0, r.x0))
    clusters: list[list] = []
    for r in rects:
        placed = False
        for c in clusters:
            u = _union_rects(c + [r])
            # 若扩展后仍紧凑则并入
            if u and (u.y1 - c[-1].y0) < max(40, r.height * 2):
                c.append(r)
                placed = True
                break
        if not placed:
            clusters.append([r])

    page_area = abs(page.rect.width * page.rect.height) or 1.0
    long_texts = _long_text_rects(page)
    tables = _table_rects(page)
    safe: list = []
    for c in clusters:
        u = _union_rects(c)
        if u is None or u.is_empty:
            continue
        # 轻微外扩
        u = pymupdf.Rect(u.x0 - 2, u.y0 - 2, u.x1 + 2, u.y1 + 2) & page.rect
        area_frac = abs(u.width * u.height) / page_area
        if area_frac > MAX_AREA_FRAC:
            continue  # 绝不退回整页
        # 正文防触碰
        text_hit = 0.0
        for tr in long_texts:
            text_hit = max(text_hit, _overlap_ratio(u, tr))
        if text_hit > TEXT_OVERLAP_MAX:
            continue
        # 表格避让
        table_hit = any(_overlap_ratio(u, tb) > 0.2 for tb in tables)
        if table_hit:
            continue
        # 最小尺寸
        if u.width < 80 or u.height < 60:
            continue
        safe.append(u)
    return safe


def crop_png(page, rect, *, dpi: int | None = None, max_px: int | None = None) -> bytes:
    """区域栅格化；长边超 max_px 时自动降 DPI。"""
    dpi = int(dpi or VECTOR_CROP_DPI)
    max_px = int(max_px or VECTOR_MAX_PX)
    r = pymupdf.Rect(rect)
    # 估算像素
    w_px = r.width * dpi / 72.0
    h_px = r.height * dpi / 72.0
    long_px = max(w_px, h_px)
    if long_px > max_px:
        dpi = max(72, int(dpi * max_px / long_px))
    pix = page.get_pixmap(clip=r, dpi=dpi, alpha=False)
    return pix.tobytes("png")
