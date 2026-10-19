#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-079：为 plan079-locate-check.mjs 生成多页 PDF 夹具（源文 5 页、译文 5 页和 3 页）。

    python3 scripts/browser/plan079_make_pdfs.py OUT_DIR
"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf


def main() -> int:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for name, pages in (("source", 5), ("translated5", 5), ("translated3", 3)):
        doc = pymupdf.open()
        for n in range(1, pages + 1):
            page = doc.new_page(width=600, height=800)
            page.insert_text((72, 120), f"{name} page {n}", fontsize=28)
        doc.save(str(out / f"{name}.pdf"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
