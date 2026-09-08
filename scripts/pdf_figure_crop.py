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
# PLAN-029b：幻灯页 profile（17 页 16:9 样本标定：8→12 区域，无整页覆盖）
SLIDE_TEXT_OVERLAP = float(os.environ.get("QYUNSLATION_SLIDE_TEXT_OVERLAP", "0.50"))
SLIDE_MAX_AREA_FRAC = float(os.environ.get("QYUNSLATION_SLIDE_MAX_AREA_FRAC", "0.80"))
SLIDE_MIN_DRAWINGS = int(os.environ.get("QYUNSLATION_SLIDE_MIN_DRAWINGS", "6"))


def is_slide_page(page) -> bool:
    """16:9 / 4:3 幻灯；与 Hermes lit_tables.is_slide_page 口径一致。"""
    r = page.rect
    return bool(r.height) and r.width / r.height >= 1.55


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


def table_rects(page) -> list:
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


_table_rects = table_rects  # backward compat


def _overlap_ratio(a, b) -> float:
    inter = pymupdf.Rect(a) & pymupdf.Rect(b)
    if inter.is_empty:
        return 0.0
    area_a = abs(a.width * a.height) or 1.0
    return abs(inter.width * inter.height) / area_a


def page_caption_profile(page) -> dict:
    """PLAN-030c：页型 = pure_table | figure_only | mixed | none。"""
    try:
        from qyunslation.structure.captions import caption_anchors

        anchors = caption_anchors(page)
    except Exception:
        anchors = []
    figs = [a for a in anchors if a[0] == "figure"]
    tabs = [a for a in anchors if a[0] == "table"]
    if tabs and not figs:
        kind = "pure_table"
    elif figs and not tabs:
        kind = "figure_only"
    elif figs and tabs:
        kind = "mixed"
    else:
        kind = "none"
    return {"figure_caps": figs, "table_caps": tabs, "page_kind": kind}


def _merge_by_figure_captions(page, candidates: list, caps: list) -> list:
    if not candidates:
        return []
    if not caps:
        return list(candidates)
    page_area = abs(page.rect.width * page.rect.height) or 1.0
    caps_sorted = sorted(caps, key=lambda x: x[2])
    groups: dict[int, list] = {}
    for u in candidates:
        owner = None
        for _kind, num, y0, _bb in caps_sorted:
            if u.y1 <= y0 + 12:
                owner = num
                break
        if owner is None:
            owner = caps_sorted[-1][1]
        groups.setdefault(owner, []).append(u)
    out = []
    for _num, us in sorted(groups.items()):
        merged = _union_rects(us)
        if merged is None or merged.is_empty:
            continue
        merged = pymupdf.Rect(merged) & page.rect
        area_frac = abs(merged.width * merged.height) / page_area
        if area_frac > MAX_AREA_FRAC:
            out.extend(us)
            continue
        if merged.width >= 80 and merged.height >= 60:
            out.append(merged)
    return out


def _page_bitmap_rects(page, exclude_rects: Iterable | None = None) -> list:
    exclude = [pymupdf.Rect(r) for r in (exclude_rects or [])]
    out = []
    try:
        infos = page.get_image_info(xrefs=True) or []
    except Exception:
        return out
    for info in infos:
        bbox = info.get("bbox")
        if not bbox:
            continue
        rr = pymupdf.Rect(bbox) & page.rect
        if rr.is_empty or rr.width < 40 or rr.height < 40:
            continue
        if any(_overlap_ratio(rr, ex) > 0.45 for ex in exclude):
            continue
        out.append(rr)
    return out


def labeled_figure_regions(page, exclude_rects: Iterable | None = None) -> dict[int, object]:
    """按 Figure 编号归组后的区域。无题注页返回空（不把匿名矢量当语义图）。"""
    profile = page_caption_profile(page)
    if not profile["figure_caps"]:
        return {}
    regions = find_figure_regions(page, exclude_rects)
    caps_sorted = sorted(profile["figure_caps"], key=lambda x: x[2])
    out: dict[int, object] = {}
    for u in regions:
        owner = None
        for _kind, num, y0, _bb in caps_sorted:
            if u.y1 <= y0 + 12:
                owner = num
                break
        if owner is None:
            owner = caps_sorted[-1][1]
        if owner in out:
            merged = _union_rects([out[owner], u])
            if merged is not None:
                out[owner] = pymupdf.Rect(merged) & page.rect
        else:
            out[owner] = u
    return out


def find_figure_regions(page, exclude_rects: Iterable | None = None) -> list:
    """PLAN-030c 规则 A–D：题注驱动的可译区域（矢量 + 位图归组）。"""
    if pymupdf is None:
        return []
    profile = page_caption_profile(page)
    if profile["page_kind"] == "pure_table":
        return []
    if profile["page_kind"] == "none":
        return find_safe_vector_figures(page, exclude_rects=exclude_rects)
    tables = [] if profile["page_kind"] == "figure_only" else None
    candidates = list(
        find_safe_vector_figures(
            page,
            exclude_rects=exclude_rects,
            tables=tables,
            min_drawings=2,
        )
    )
    candidates.extend(_page_bitmap_rects(page, exclude_rects))
    return _merge_by_figure_captions(page, candidates, profile["figure_caps"])


NESTED_COVER_FRAC = float(os.environ.get("QYUNSLATION_NESTED_COVER_FRAC", "0.90"))


def _drop_nested(rects: list) -> list:
    """丢弃被更大区域覆盖 ≥90% 的嵌套框。

    PLAN-030d：legacy 聚类在同一处会同时给出父框与子框（如 ljae439 p2），
    导致预扫描与执行重复计数同一张图。按面积降序保留最大者。
    """
    out: list = []
    for r in sorted(rects, key=lambda x: abs(x), reverse=True):
        area = abs(r)
        if area <= 0:
            continue
        if any(abs(r & bigger) / area >= NESTED_COVER_FRAC for bigger in out):
            continue
        out.append(r)
    return out


def translatable_regions(page, exclude_rects: Iterable | None = None) -> list:
    """预扫描与执行共用的可译区域口径（PLAN-027 不变量 4）。

    幻灯页无题注，必须走 PLAN-029b profile；否则预扫描报 0 而执行仍会嵌字。
    """
    if is_slide_page(page):
        regions = find_safe_vector_figures(
            page,
            exclude_rects=exclude_rects,
            tables=[],
            text_overlap_max=SLIDE_TEXT_OVERLAP,
            max_area_frac=SLIDE_MAX_AREA_FRAC,
            min_drawings=SLIDE_MIN_DRAWINGS,
        )
    else:
        regions = find_figure_regions(page, exclude_rects=exclude_rects)
    return _drop_nested(regions)


def find_safe_vector_figures(
    page,
    exclude_rects: Iterable | None = None,
    *,
    tables: list | None = None,
    text_overlap_max: float | None = None,
    max_area_frac: float | None = None,
    min_drawings: int | None = None,
) -> list:
    """定位可安全栅格化覆盖的矢量设计图区域。不确定则返回空（Fail-Closed）。"""
    if pymupdf is None:
        return []
    overlap_max = TEXT_OVERLAP_MAX if text_overlap_max is None else text_overlap_max
    area_max = MAX_AREA_FRAC if max_area_frac is None else max_area_frac
    min_dr = MIN_DRAWINGS if min_drawings is None else min_drawings
    exclude = [pymupdf.Rect(r) for r in (exclude_rects or [])]
    try:
        drawings = page.get_drawings() or []
    except Exception:
        return []
    if len(drawings) < min_dr:
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
    if len(rects) < min_dr:
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
    if tables is None:
        tables = table_rects(page)
    safe: list = []
    for c in clusters:
        u = _union_rects(c)
        if u is None or u.is_empty:
            continue
        # 轻微外扩
        u = pymupdf.Rect(u.x0 - 2, u.y0 - 2, u.x1 + 2, u.y1 + 2) & page.rect
        area_frac = abs(u.width * u.height) / page_area
        if area_frac > area_max:
            continue  # 绝不退回整页
        # 正文防触碰
        text_hit = 0.0
        for tr in long_texts:
            text_hit = max(text_hit, _overlap_ratio(u, tr))
        if text_hit > overlap_max:
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
