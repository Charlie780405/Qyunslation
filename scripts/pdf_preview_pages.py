#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-033e：当前页 300 DPI，其它页低 DPI 占位。"""
from __future__ import annotations

from pathlib import Path

PREVIEW_HI_DPI = 300
PREVIEW_LO_DPI = 72


def page_pixel_size(page, dpi: int) -> tuple[int, int]:
    return (
        max(1, int(round(float(page.rect.width) * dpi / 72.0))),
        max(1, int(round(float(page.rect.height) * dpi / 72.0))),
    )


def render_preview_pages(
    src: Path | str,
    current_page: int,
    *,
    dest_dir: Path | str,
    hi_dpi: int = PREVIEW_HI_DPI,
    lo_dpi: int = PREVIEW_LO_DPI,
) -> dict[int, Path]:
    """current_page 为 1-based。只把当前页打到 hi_dpi，其余 lo_dpi。"""
    import pymupdf

    src = Path(src)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    out: dict[int, Path] = {}
    doc = pymupdf.open(src)
    try:
        for index, page in enumerate(doc, start=1):
            dpi = hi_dpi if index == current_page else lo_dpi
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            path = dest / f"page-{index}-{dpi}.png"
            pix.save(path)
            out[index] = path
    finally:
        doc.close()
    return out
