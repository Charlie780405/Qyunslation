#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-008c：模板 load / detect / apply。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import doc_profile  # noqa: E402


class TestDocProfile(unittest.TestCase):
    def test_load_four_profiles(self):
        data = doc_profile.load()
        self.assertEqual(set(data), {"letter", "literature", "regulatory", "generic"})
        self.assertTrue(data["letter"]["merge_aggressive"])
        self.assertFalse(data["regulatory"]["merge_aggressive"])
        self.assertEqual(data["literature"]["primary_font_family"], "serif")

    def test_detect_letter_from_filename(self):
        self.assertEqual(doc_profile.name_from_choice("自动"), "auto")
        # 文件名含 PIND，即使文件不存在也走 letter（detect 读失败仍用 name）
        blob_name = "FDA responses on PIND.pdf"
        self.assertTrue(doc_profile._LETTER_RE.search(blob_name))

    def test_detect_literature_from_text(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest("pymupdf missing")
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "paper.pdf"
            doc = pymupdf.open()
            page = doc.new_page()
            page.insert_text((72, 72), "Abstract\nDOI: 10.1000/xyz\nReferences")
            doc.save(p)
            doc.close()
            self.assertEqual(doc_profile.detect(p), "literature")

    def test_apply_writes_settings(self):
        settings = SimpleNamespace(
            translation=SimpleNamespace(primary_font_family=None),
            pdf=SimpleNamespace(
                split_short_lines=False,
                short_line_split_factor=0.8,
                disable_rich_text_translate=True,
                no_merge_alternating_line_numbers=False,
            ),
        )
        prof = doc_profile.apply("regulatory", settings)
        self.assertEqual(prof["name"], "regulatory")
        self.assertEqual(settings.translation.primary_font_family, "sans-serif")
        self.assertTrue(settings.pdf.no_merge_alternating_line_numbers)
        self.assertFalse(settings.pdf.split_short_lines)

    def test_resolve_manual_overrides_auto(self):
        self.assertEqual(doc_profile.resolve("学术文献", None), "literature")
        self.assertEqual(doc_profile.resolve("自动", Path("/tmp/FDA-PIND.pdf")), "letter")


if __name__ == "__main__":
    unittest.main()
