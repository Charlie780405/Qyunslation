#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""译后回插图形区（PLAN-010c）。ocr_workaround 会丢掉 OCR PDF 内嵌图。"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _near(a: float, b: float, tol: float = 3.0) -> bool:
    return abs(a - b) <= tol


def reinsert(
    pdf: Path,
    manifest: Path,
    *,
    dual_left: bool = True,
    kinds: set[str] | None = None,
) -> int:
    """把 manifest 中的 PNG 插回译文 PDF。返回新插入张数。幂等。

    kinds: 只回插这些 kind（如 {"logo","stamp"}）；None 表示全部。
    """
    import pymupdf

    pdf = Path(pdf)
    manifest = Path(manifest)
    if not pdf.is_file() or not manifest.is_file():
        logger.warning("graphic_reinsert 跳过：缺文件 pdf=%s mf=%s", pdf, manifest)
        return 0

    data = json.loads(manifest.read_text(encoding="utf-8"))
    if str(manifest).endswith(".graphics.json"):
        gdir = Path(str(manifest)[: -len(".json")])  # foo.pdf.graphics
    else:
        gdir = Path(str(manifest).removesuffix(".json"))
    if not gdir.is_dir():
        gdir = Path(str(pdf) + ".graphics")

    doc = pymupdf.open(pdf)
    inserted = 0
    for page_info in data.get("pages") or []:
        page_no = int(page_info["page"])
        src_w, src_h = page_info.get("size") or [0, 0]
        if page_no < 1 or page_no > len(doc):
            continue
        page = doc[page_no - 1]
        pw = page.rect.width
        # mono ≈ src_w；dual ≈ 2×src_w（译文在左）
        is_mono = _near(pw, float(src_w), tol=8.0)
        is_dual = _near(pw, float(src_w) * 2.0, tol=12.0)
        if not is_mono and not is_dual:
            logger.warning(
                "graphic_reinsert 页宽不匹配 page=%s pw=%.1f src_w=%.1f，跳过",
                page_no,
                pw,
                src_w,
            )
            continue
        if is_dual and not dual_left:
            continue

        existing = page.get_image_info() or []
        for reg in page_info.get("regions") or []:
            kind = str(reg.get("kind") or "graphic")
            if kinds is not None and kind not in kinds:
                continue
            box = reg["box"]
            png_name = reg.get("png") or ""
            png_path = gdir / png_name
            if not png_path.is_file():
                logger.warning("缺 PNG %s", png_path)
                continue
            x0, y0, x1, y1 = map(float, box)
            rect = pymupdf.Rect(x0, y0, x1, y1)
            # 幂等：同位置同尺寸已有图则跳过
            already = False
            for info in existing:
                bbox = info.get("bbox")
                if not bbox:
                    continue
                if (
                    _near(bbox[0], x0)
                    and _near(bbox[1], y0)
                    and _near(bbox[2], x1)
                    and _near(bbox[3], y1)
                ):
                    already = True
                    break
            if already:
                continue
            page.insert_image(
                rect,
                filename=str(png_path),
                overlay=True,
                keep_proportion=True,
            )
            inserted += 1
            existing = page.get_image_info() or []

    if inserted:
        tmp = pdf.with_suffix(pdf.suffix + ".reinsert.tmp")
        doc.save(tmp, deflate=True, garbage=3)
        doc.close()
        tmp.replace(pdf)
    else:
        doc.close()
    logger.info("graphic_reinsert %s +%s", pdf, inserted)
    return inserted


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="译后回插 graphics manifest")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("manifest", type=Path, nargs="?", default=None)
    args = ap.parse_args()
    mf = args.manifest
    if mf is None:
        mf = Path(str(args.pdf) + ".graphics.json")
        # OCR PDF 常与译文不同名：尝试同 stem 旁路
        if not mf.is_file():
            cand = Path(str(args.pdf).replace(".mono.pdf", ".hpd-ocr.pdf") + ".graphics.json")
            if cand.is_file():
                mf = cand
    n = reinsert(args.pdf, mf)
    print(f"inserted={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
