#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-005a smoke：mock HPD，测 pdf_needs_hpd 与坐标块解析。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import hpd_ocr  # noqa: E402


class TestHpdOcr(unittest.TestCase):
    def test_blocks_parse(self):
        raw = (
            "<BLOCK>Text [10, 20, 100, 40]<CHILD>Hello\n"
            "<BLOCK>Text [1, 2, 3, 4]<CHILD>[Non-Text]\n"
        )
        blocks = hpd_ocr._blocks(raw)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0][4], "Hello")

    def test_blocks_strips_html_and_splits_table(self):
        raw = (
            "<BLOCK>table [0, 0, 100, 40]<CHILD>"
            "<table><tr><td>提前终止</td><td>标准一</td></tr></table>\n"
        )
        blocks = hpd_ocr._blocks(raw)
        texts = [b[4] for b in blocks]
        self.assertEqual(texts, ["提前终止", "标准一"])
        self.assertTrue(all("<" not in t for t in texts))

    def test_insert_preserves_cjk(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest("pymupdf missing")
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.pdf"
            dest = Path(td) / "out.pdf"
            doc = pymupdf.open()
            doc.new_page()
            doc.save(src)
            doc.close()
            html = (
                "<BLOCK>table [10, 10, 400, 200]<CHILD>"
                "<table><tr><td>提前终止研究治疗标准</td><td>受试者</td></tr></table>\n"
            )
            with patch.object(hpd_ocr, "_parse", return_value=html):
                hpd_ocr.ocr_pdf_with_hpd(src, dest)
            out = pymupdf.open(dest)
            extracted = "".join((out[0].get_text() or "").split())
            out.close()
            self.assertIn("提前终止", extracted)
            self.assertNotIn("<table", extracted)
            self.assertNotIn("????", extracted)

    def test_pdf_needs_hpd_empty(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest("pymupdf missing")
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "blank.pdf"
            doc = pymupdf.open()
            doc.new_page()
            doc.save(p)
            doc.close()
            self.assertTrue(hpd_ocr.pdf_needs_hpd(p, min_chars=80))

    def test_ocr_raises_when_no_text(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest("pymupdf missing")
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "blank.pdf"
            out = Path(td) / "out.pdf"
            doc = pymupdf.open()
            doc.new_page()
            doc.save(p)
            doc.close()
            with patch.object(hpd_ocr, "_parse", return_value=""):
                with self.assertRaises(RuntimeError):
                    hpd_ocr.ocr_pdf_with_hpd(p, out)

    def test_fit_fontsize_wide_flat_block(self):
        """PLAN-007b：宽扁 box 塞长文本时字号中位数须 ≥ 8pt（不塌到 5pt 地板）。"""
        try:
            import pymupdf
            import statistics
        except ImportError:
            self.skipTest("pymupdf missing")
        long = (
            "You should provide, to the Regulatory Project Manager, "
            "a copy of any revised documentation or additional information "
            "for the official record of this meeting will be the official record."
        )
        # HPD 归一化坐标：宽扁单行盒（旧公式会塌到 5pt）
        raw = f"<BLOCK>Text [50, 400, 950, 420]<CHILD>{long}\n"
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.pdf"
            dest = Path(td) / "out.pdf"
            doc = pymupdf.open()
            # A4，配合 150dpi pixmap 宽度会 >1200 触发 0–1000 归一化
            doc.new_page(width=595, height=842)
            doc.save(src)
            doc.close()
            with patch.object(hpd_ocr, "_parse", return_value=raw):
                hpd_ocr.ocr_pdf_with_hpd(src, dest, dpi=150)
            out = pymupdf.open(dest)
            sizes = []
            for b in out[0].get_text("dict")["blocks"]:
                for line in b.get("lines", []):
                    for s in line["spans"]:
                        if s.get("text", "").strip():
                            sizes.append(float(s["size"]))
            out.close()
            self.assertTrue(sizes, "expected OCR text spans")
            median = statistics.median(sizes)
            self.assertGreaterEqual(median, 8.0, f"font median {median} < 8")
            self.assertGreaterEqual(min(sizes), 7.0, f"font min {min(sizes)} < 7")

    def test_fit_fontsize_helper(self):
        font = hpd_ocr._pymupdf_font()
        text = "Hello world " * 20
        fs = hpd_ocr._fit_fontsize(font, text, box_w=400.0, box_h=40.0)
        self.assertGreaterEqual(fs, 7.0)
        self.assertLessEqual(fs, 28.0)


if __name__ == "__main__":
    unittest.main()
