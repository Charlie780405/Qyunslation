#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import letter_pipeline as lp  # noqa: E402


class TestLetterPipeline(unittest.TestCase):
    def test_reflow_uses_existing_zh(self):
        import pymupdf

        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            src = tdir / "in.pdf"
            doc = pymupdf.open()
            doc.new_page(width=595, height=842)
            doc.save(src)
            doc.close()
            dbg = tdir / "in.hpd-ocr.pdf.hpd-debug.json"
            dbg.write_text(
                json.dumps(
                    {
                        "pages": [
                            {
                                "items": [
                                    {
                                        "role": "body",
                                        "text": "Question 1: Hello",
                                        "text_zh": "问题1：你好。",
                                        "box": [67, 120, 500, 160],
                                    },
                                    {
                                        "role": "footer",
                                        "text": "Reference ID: 1",
                                        "box": [67, 760, 300, 780],
                                    },
                                ]
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            dest = tdir / "out.pdf"
            lp.translate_scanned_letter(src, dbg, dest)
            self.assertTrue(dest.is_file())
            text = pymupdf.open(dest)[0].get_text()
            self.assertIn("问题1", text)


if __name__ == "__main__":
    unittest.main()
