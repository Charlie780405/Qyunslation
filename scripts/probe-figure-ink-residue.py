#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-038f：Figure 像素残影探针（WARN，不 block release）。

比较原文/译文 pixmap 在 figure bbox 内：原文有墨迹、译文仍接近原文墨迹色的像素占比。
超过阈值 → WARN（exit 2）；无法比较 → SKIP（exit 0）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _ink_mask(pix, thresh: int = 40):
    import numpy as np

    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    rgb = arr[:, :, :3].astype(int)
    # 非近白像素视为墨迹
    return (rgb.max(axis=2) < 255 - thresh)


def probe_figure_residue(
    original_pdf: Path,
    translated_pdf: Path,
    *,
    page_index: int = 0,
    bbox: tuple[float, float, float, float] | None = None,
    residue_frac_warn: float = 0.08,
) -> dict:
    import pymupdf

    src = pymupdf.open(original_pdf)
    dst = pymupdf.open(translated_pdf)
    try:
        sp = src[page_index]
        dp = dst[page_index]
        clip = pymupdf.Rect(*bbox) if bbox else sp.rect
        spix = sp.get_pixmap(clip=clip, dpi=72, alpha=False)
        dpix = dp.get_pixmap(clip=clip, dpi=72, alpha=False)
        if spix.width != dpix.width or spix.height != dpix.height:
            return {"status": "skip", "reason": "size_mismatch"}
        import numpy as np

        s_ink = _ink_mask(spix)
        d_ink = _ink_mask(dpix)
        s_arr = np.frombuffer(spix.samples, dtype=np.uint8).reshape(spix.h, spix.w, spix.n)[:, :, :3]
        d_arr = np.frombuffer(dpix.samples, dtype=np.uint8).reshape(dpix.h, dpix.w, dpix.n)[:, :, :3]
        # 原文有墨、译文仍接近原文 RGB → 疑似未擦净残影
        near = (np.abs(s_arr.astype(int) - d_arr.astype(int)).max(axis=2) <= 12) & s_ink & d_ink
        ink_n = int(s_ink.sum())
        if ink_n < 20:
            return {"status": "skip", "reason": "too_little_source_ink", "source_ink": ink_n}
        frac = float(near.sum()) / float(ink_n)
        status = "warn" if frac >= residue_frac_warn else "ok"
        return {
            "status": status,
            "residue_frac": round(frac, 4),
            "source_ink": ink_n,
            "threshold": residue_frac_warn,
            "page": page_index,
            "bbox": list(bbox) if bbox else None,
        }
    finally:
        src.close()
        dst.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original")
    parser.add_argument("translated")
    parser.add_argument("--page", type=int, default=0)
    parser.add_argument("--bbox", type=float, nargs=4, default=None)
    parser.add_argument("--threshold", type=float, default=0.08)
    args = parser.parse_args(argv)
    result = probe_figure_residue(
        Path(args.original),
        Path(args.translated),
        page_index=args.page,
        bbox=tuple(args.bbox) if args.bbox else None,
        residue_frac_warn=args.threshold,
    )
    print(json.dumps(result, ensure_ascii=False))
    if result.get("status") == "warn":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
