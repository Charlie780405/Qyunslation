#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-010c：图形区检测与回插夹具。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import graphic_regions as gr  # noqa: E402
import graphic_reinsert as gi  # noqa: E402

PAGE1 = Path("/home/dev/pdf2zh/bench/007/page1.pdf")


@unittest.skipUnless(PAGE1.is_file(), "page1.pdf missing")
class TestGraphicRegions(unittest.TestCase):
    def test_detect_logo_on_page1(self):
        import pymupdf

        doc = pymupdf.open(PAGE1)
        page = doc[0]
        # 粗略文字盒：中间正文区，擦掉后顶部 logo 仍应在
        text_boxes = [(60, 160, 540, 780)]
        regs = gr.detect(page, text_boxes, dpi=100)
        doc.close()
        logos = [r for r in regs if r.kind == "logo"]
        self.assertGreaterEqual(len(logos), 1, msg=f"regs={regs}")
        x0, y0, x1, y1 = logos[0].box
        self.assertLess(x0, 0.5 * 595.32)
        self.assertLess(y1, 0.25 * 841.92)

    def test_text_area_not_detected(self):
        import pymupdf
        import numpy as np

        doc = pymupdf.open(PAGE1)
        page = doc[0]
        # 擦掉整页墨迹 → 不应检出
        # 用覆盖全页的 text_boxes 模拟
        regs = gr.detect(page, [(0, 0, page.rect.width, page.rect.height)], dpi=100)
        doc.close()
        self.assertEqual(regs, [])

    def test_reinsert_idempotent(self):
        import pymupdf
        import shutil

        if not PAGE1.is_file():
            self.skipTest("no page1")
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            pdf = td / "t.pdf"
            shutil.copy2(PAGE1, pdf)
            doc = pymupdf.open(pdf)
            page = doc[0]
            regs = gr.detect(page, [(60, 200, 540, 800)], dpi=100)
            doc.close()
            self.assertTrue(regs)
            pages = {1: regs}
            mf = gr.write_manifest(pdf, PAGE1, pages, dpi=150)
            n1 = gi.reinsert(pdf, mf)
            n2 = gi.reinsert(pdf, mf)
            self.assertGreaterEqual(n1, 1)
            self.assertEqual(n2, 0)


if __name__ == "__main__":
    unittest.main()
