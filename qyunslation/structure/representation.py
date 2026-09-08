# SPDX-License-Identifier: MPL-2.0
"""PLAN-030d Task 9：原生 / 扫描 / 混合 PDF 的逐页判定。

`hpd_ocr.pdf_needs_hpd` 是整档判定（全文档字符数 < 80），部分页扫描的混合件会
被一刀切。这里逐页判定，文档级形态由页级结果归纳。
"""
from __future__ import annotations

from .models import Representation

# 页面文字少于此字符数即认为没有可用文字层
MIN_PAGE_CHARS = 20
# 单张图覆盖页面达到此比例即认为是整页扫描图。
# 实测：FDA PIND 0.75、Abstract 1.00；原生件 ljae439 最大 0.22、Nature 0。
SCAN_IMAGE_COVER = 0.60


def _max_image_cover(page) -> float:
    """最大图片的页面覆盖比。

    走 `get_text("dict")` 的图像块 bbox 而非 `get_image_rects()`——后者要按
    xref 反查内容流，在 FDA PIND 这类每页两张大图的扫描件上实测 20 页要 17s，
    会吃掉 Tier-3 的整个预算。
    """
    area = page.rect.get_area()
    if area <= 0:
        return 0.0
    try:
        blocks = page.get_text("dict").get("blocks", [])
    except Exception:
        return 0.0
    best = 0.0
    for block in blocks:
        if block.get("type") != 1:
            continue
        bbox = block.get("bbox")
        if not bbox:
            continue
        width = max(0.0, float(bbox[2]) - float(bbox[0]))
        height = max(0.0, float(bbox[3]) - float(bbox[1]))
        best = max(best, (width * height) / area)
    return best


def page_representation(page) -> Representation:
    """单页形态。

    原生页（有文字、无整页大图）零图片解码开销——这是最常见的情况，不能为了
    判定形态拖慢 Tier-3 预扫描。
    """
    try:
        chars = len((page.get_text() or "").strip())
    except Exception:
        chars = 0
    if chars < MIN_PAGE_CHARS:
        # 没有文字层就得走 OCR，无须再量图片覆盖
        return Representation.SCANNED
    if _max_image_cover(page) >= SCAN_IMAGE_COVER:
        # 有文字层又压着整页扫描图，是 OCR 之后的产物
        return Representation.HYBRID
    return Representation.NATIVE_TEXT


def document_representation(page_modes: list[Representation]) -> Representation:
    """由页级形态归纳文档形态。混合件不一刀切。"""
    if not page_modes:
        return Representation.NATIVE_TEXT
    distinct = set(page_modes)
    if distinct == {Representation.SCANNED}:
        return Representation.SCANNED
    if distinct == {Representation.NATIVE_TEXT}:
        return Representation.NATIVE_TEXT
    return Representation.HYBRID


def needs_ocr(page_modes: list[Representation]) -> bool:
    """是否有页面缺文字层，需要 HPD OCR 兜底。"""
    return Representation.SCANNED in page_modes
