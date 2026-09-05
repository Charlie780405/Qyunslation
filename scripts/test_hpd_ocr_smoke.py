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

    def test_merge_lines_joins_are_enclosed(self):
        """PLAN-008b：are / enclosed 半句须落在同一段落块。"""
        # 模拟页 1 正文列（点坐标已缩放过）
        lines = [
            (67.0, 327.0, 512.0, 358.0,
             "Please refer to your pre-investigational new drug application (PIND) file for GS301."),
            (67.0, 340.0, 540.0, 418.0,
             "We also refer to your correspondence, received June 12, 2026, requesting a meeting to"),
            (67.0, 361.0, 531.0, 378.0,
             "discuss the proposed regulatory strategy, the comparative analytical assessment strategy,"),
            (67.0, 381.0, 527.0, 398.0,
             "and the non-clinical and clinical development plan to support the development of GS301"),
            (67.0, 401.0, 524.0, 418.0,
             "as a biosimilar to US-Vabysmo. Our preliminary responses to your meeting questions are"),
            (67.0, 420.0, 471.0, 438.0,
             "enclosed. You should provide, to the Regulatory Project Manager, an electronic version of any"),
            (67.0, 440.0, 474.0, 456.0,
             "materials (i.e., slides or handouts) to be presented and/or discussed at the meeting."),
            # 独立标题行（大 gap）
            (67.0, 300.0, 191.0, 316.0, "Dear Dr. Mei-Fei Yueh:"),
            # 签名列
            (234.0, 529.0, 285.0, 546.0, "Sincerely,"),
            (234.0, 556.0, 453.0, 573.0, "{See appended electronic signature page)"),
        ]
        # 按 y 排好再测
        lines = sorted(lines, key=lambda b: (b[1], b[0]))
        merged = hpd_ocr._merge_lines_into_paragraphs(lines, aggressive=True)
        texts = [m[4] for m in merged]
        joined = " ".join(texts)
        self.assertIn("questions are enclosed.", joined)
        # 不应再出现单独以 are 结尾的块
        for t in texts:
            self.assertFalse(
                t.rstrip().endswith(" questions are"),
                f"半句未合并: {t!r}",
            )
        self.assertLess(len(merged), len(lines))
        # Dear / Sincerely / 首段 保持独立
        self.assertTrue(any(t.startswith("Dear") for t in texts))
        self.assertTrue(any(t.startswith("Sincerely") for t in texts))
        self.assertTrue(
            any(t.startswith("Please refer") and "enclosed" not in t for t in texts)
            or any("GS301." in t and "enclosed" not in t for t in texts),
            texts,
        )

    def test_merge_conservative_breaks_on_period(self):
        """regulatory：aggressive=False 时句号即断段。"""
        lines = [
            (10.0, 10.0, 200.0, 25.0, "First sentence ends here."),
            (10.0, 26.0, 200.0, 41.0, "Second sentence starts."),
        ]
        merged = hpd_ocr._merge_lines_into_paragraphs(lines, aggressive=False)
        self.assertEqual(len(merged), 2)

    def test_merge_does_not_join_table_cells_different_x(self):
        """不同列（表格单元格）不因纵向接近而合并。"""
        lines = [
            (10.0, 10.0, 80.0, 25.0, "提前终止"),
            (100.0, 10.0, 200.0, 25.0, "标准一"),
            (10.0, 30.0, 80.0, 45.0, "下一行左"),
            (100.0, 30.0, 200.0, 45.0, "下一行右"),
        ]
        merged = hpd_ocr._merge_lines_into_paragraphs(lines, aggressive=False)
        texts = {m[4] for m in merged}
        self.assertIn("提前终止", texts)
        self.assertIn("标准一", texts)
        self.assertIn("下一行左", texts)
        self.assertIn("下一行右", texts)
        self.assertFalse(any("提前终止" in t and "标准一" in t for t in texts))


if __name__ == "__main__":
    unittest.main()
