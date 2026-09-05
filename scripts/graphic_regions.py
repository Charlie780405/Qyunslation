#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""扫描页图形区检测与裁切（PLAN-010c）。译后回插见 graphic_reinsert。"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Region:
    box: tuple[float, float, float, float]  # PDF pt (x0,y0,x1,y1)
    kind: str  # logo | stamp | graphic
    suppress_text: bool
    png: str  # 文件名


def _to_gray_array(page, *, dpi: int):
    import numpy as np
    import pymupdf

    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    return arr, pix.width, pix.height


def _erase_text(
    ink,
    text_boxes: Sequence[tuple[float, float, float, float]],
    *,
    dpi: int,
    pad_pt: float = 3.5,
):
    scale = dpi / 72.0
    pad = pad_pt * scale
    h, w = ink.shape
    for x0, y0, x1, y1 in text_boxes:
        px0 = max(0, int(x0 * scale - pad))
        py0 = max(0, int(y0 * scale - pad))
        px1 = min(w, int(x1 * scale + pad))
        py1 = min(h, int(y1 * scale + pad))
        if px1 > px0 and py1 > py0:
            ink[py0:py1, px0:px1] = False


def passes_filter(png: bytes, w_pt: float, h_pt: float) -> bool:
    """空白率 / 尺寸过滤（lit-figures 同款精神）。"""
    if min(w_pt, h_pt) < 18.0:
        return False
    if w_pt * h_pt < 400.0:
        return False
    try:
        import io

        import numpy as np
        from PIL import Image

        im = Image.open(io.BytesIO(png)).convert("L")
        arr = np.asarray(im, dtype=np.uint8)
        blank = float((arr > 245).mean()) if arr.size else 1.0
        if blank > 0.985:
            return False
    except Exception as exc:
        logger.warning("passes_filter 跳过图像检查: %s", exc)
    return True


def crop(page, region: Region, *, dpi: int = 300) -> bytes:
    import pymupdf

    x0, y0, x1, y1 = region.box
    pix = page.get_pixmap(clip=pymupdf.Rect(x0, y0, x1, y1), dpi=dpi)
    return pix.tobytes("png")


def detect(
    page,
    text_boxes: Sequence[tuple[float, float, float, float]],
    *,
    dpi: int = 150,
    page_frac_max: float = 0.35,
) -> list[Region]:
    """连通域检测 logo/印章/图形。失败返回 []。"""
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        logger.warning("graphic_regions 缺依赖: %s", exc)
        return []

    try:
        gray, pw_px, ph_px = _to_gray_array(page, dpi=dpi)
    except Exception as exc:
        logger.warning("graphic_regions 渲染失败: %s", exc)
        return []

    page_w = float(page.rect.width)
    page_h = float(page.rect.height)
    scale = dpi / 72.0
    page_area = page_w * page_h

    ink = gray < 200
    _erase_text(ink, text_boxes, dpi=dpi)
    k = max(3, int(round(6 * dpi / 72)))
    kernel = np.ones((k, k), np.uint8)
    closed = cv2.morphologyEx(ink.astype(np.uint8) * 255, cv2.MORPH_CLOSE, kernel)
    n_labels, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        closed, connectivity=8
    )

    regions: list[Region] = []
    for lab in range(1, n_labels):
        x, y, bw, bh, area_px = stats[lab]
        if bw <= 0 or bh <= 0:
            continue
        x0 = x / scale
        y0 = y / scale
        x1 = (x + bw) / scale
        y1 = (y + bh) / scale
        w_pt = x1 - x0
        h_pt = y1 - y0
        area_pt = w_pt * h_pt
        if w_pt < 18 or h_pt < 18 or area_pt < 400:
            continue
        if area_pt > page_area * page_frac_max:
            continue
        component = closed[y : y + bh, x : x + bw] > 0
        ink_ratio = float(component.mean()) if component.size else 0.0
        if ink_ratio < 0.02:
            continue
        aspect = w_pt / max(h_pt, 1e-6)
        # 细长行带 ≈ 漏擦英文正文，不是插图
        if aspect > 5.0 and h_pt < 60.0:
            continue
        if y1 < 0.25 * page_h:
            kind, suppress = "logo", True
        elif 0.8 <= aspect <= 1.25 and ink_ratio > 0.35:
            kind, suppress = "stamp", True
        else:
            kind, suppress = "graphic", False
        regions.append(
            Region(
                box=(round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)),
                kind=kind,
                suppress_text=suppress,
                png="",  # 写入 manifest 时填
            )
        )
    return regions


_KEEP_OVER_LOGO_RE = re.compile(
    r"food\s*&\s*drug|u\.s\.\s*food|食品.{0,6}药品|管理局",
    re.I,
)


def drop_boxes_in_suppress(
    boxes: list[tuple[float, float, float, float, str]],
    regions: Iterable[Region],
    *,
    frac: float = 0.6,
) -> list[tuple[float, float, float, float, str]]:
    """丢弃面积 ≥ frac 落入 suppress_text 区的行。机构全称不丢。"""
    suppress = [r for r in regions if r.suppress_text]
    if not suppress:
        return boxes
    kept: list[tuple[float, float, float, float, str]] = []
    for x0, y0, x1, y1, text in boxes:
        if _KEEP_OVER_LOGO_RE.search(text or ""):
            kept.append((x0, y0, x1, y1, text))
            continue
        area = max((x1 - x0) * (y1 - y0), 1e-6)
        covered = 0.0
        for r in suppress:
            rx0, ry0, rx1, ry1 = r.box
            ox0, oy0 = max(x0, rx0), max(y0, ry0)
            ox1, oy1 = min(x1, rx1), min(y1, ry1)
            if ox1 > ox0 and oy1 > oy0:
                covered += (ox1 - ox0) * (oy1 - oy0)
        if covered / area >= frac:
            continue
        kept.append((x0, y0, x1, y1, text))
    return kept


def write_manifest(
    dest: Path,
    src: Path,
    pages: dict[int, list[Region]],
    *,
    dpi: int = 300,
) -> Path:
    """写 <dest>.graphics.json + PNG 目录。Region.png 填相对文件名。"""
    dest = Path(dest)
    src = Path(src)
    gdir = Path(str(dest) + ".graphics")
    gdir.mkdir(parents=True, exist_ok=True)
    # 清理旧 png
    for old in gdir.glob("p*-r*.png"):
        old.unlink()

    import pymupdf

    doc = pymupdf.open(src)
    page_payload = []
    for page_i, regs in sorted(pages.items()):
        page = doc[page_i - 1]
        out_regs = []
        for ri, reg in enumerate(regs):
            png_name = f"p{page_i}-r{ri}.png"
            data = crop(page, reg, dpi=dpi)
            w_pt = reg.box[2] - reg.box[0]
            h_pt = reg.box[3] - reg.box[1]
            if not passes_filter(data, w_pt, h_pt):
                logger.info("graphic 过滤丢弃 %s kind=%s", png_name, reg.kind)
                continue
            (gdir / png_name).write_bytes(data)
            out_regs.append(
                {
                    "box": list(reg.box),
                    "kind": reg.kind,
                    "suppress_text": reg.suppress_text,
                    "png": png_name,
                }
            )
        page_payload.append(
            {
                "page": page_i,
                "size": [round(page.rect.width, 2), round(page.rect.height, 2)],
                "regions": out_regs,
            }
        )
    doc.close()
    mf = Path(str(dest) + ".graphics.json")
    mf.write_text(
        json.dumps(
            {"source": str(src), "dpi": dpi, "pages": page_payload},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    logger.info("graphics manifest → %s", mf)
    return mf
