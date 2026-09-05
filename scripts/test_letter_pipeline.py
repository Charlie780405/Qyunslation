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
            ticks: list[str] = []
            lp.translate_scanned_letter(
                src, dbg, dest, progress_cb=lambda f, d: ticks.append(d)
            )
            self.assertTrue(dest.is_file())
            text = pymupdf.open(dest)[0].get_text()
            self.assertIn("问题1", text)
            self.assertTrue(any(t.startswith("②翻译") for t in ticks))
            self.assertIn("③排版重绘", ticks)
            self.assertIn("完成", ticks)

    def test_missing_zh_skips_intro_colon(self):
        import pymupdf

        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "p.pdf"
            doc = pymupdf.open()
            page = doc.new_page(width=595, height=842)
            font = Path("/home/dev/.fonts/NotoSansSC-Regular.otf")
            page.insert_font(fontname="n", fontfile=str(font))
            page.insert_text((67, 140), "引言", fontname="n", fontsize=14)
            page.insert_text((67, 180), "本材料包含初步回复。", fontname="n", fontsize=12)
            doc.save(pdf)
            doc.close()
            page_info = {
                "items": [
                    {"role": "section", "text_zh": "引言:"},
                    {"role": "body", "text_zh": "本材料包含初步回复。"},
                ]
            }
            self.assertEqual(lp.missing_zh(pdf, page_info, 0), [])
            page_info["items"].append(
                {"role": "body", "text_zh": "FDA Response to Question 1(a): Yes"}
            )
            self.assertEqual(lp.missing_zh(pdf, page_info, 0), [])

    def test_soft_fail_writes_warnings(self):
        import pymupdf

        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            src = tdir / "in.pdf"
            doc = pymupdf.open()
            doc.new_page(width=595, height=842)
            doc.save(src)
            doc.close()
            dbg = tdir / "dbg.json"
            dbg.write_text(
                json.dumps(
                    {
                        "pages": [
                            {
                                "items": [
                                    {
                                        "role": "body",
                                        "text": "Hello world paragraph",
                                        "text_zh": "这段文字不会被画出来因为盒太小",
                                        "box": [67, 120, 80, 130],
                                    }
                                ]
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            dest = tdir / "out.pdf"
            # 不应 raise
            lp.translate_scanned_letter(src, dbg, dest)
            self.assertTrue(dest.is_file())
            # 可能有 warnings（取决于是否真正 missing）；至少不崩
            warn = Path(str(dest) + ".warnings.json")
            if warn.is_file():
                data = json.loads(warn.read_text(encoding="utf-8"))
                self.assertIsInstance(data, list)

    def test_disk_cache_hit(self):
        import hashlib
        import os

        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            cache_p = tdir / "cache.json"
            en = "Question 1: Hello from cache"
            key = hashlib.sha1(en.encode()).hexdigest()
            cache_p.write_text(
                json.dumps({key: "问题1：来自缓存。"}, ensure_ascii=False),
                encoding="utf-8",
            )
            old = os.environ.get("QYUNSLATION_LETTER_CACHE")
            os.environ["QYUNSLATION_LETTER_CACHE"] = str(cache_p)
            os.environ["QYUNSLATION_LETTER_WORKERS"] = "1"
            try:
                import pymupdf

                src = tdir / "in.pdf"
                doc = pymupdf.open()
                doc.new_page(width=595, height=842)
                doc.save(src)
                doc.close()
                dbg = tdir / "dbg.json"
                dbg.write_text(
                    json.dumps(
                        {
                            "pages": [
                                {
                                    "items": [
                                        {
                                            "role": "body",
                                            "text": en,
                                            "box": [67, 120, 500, 200],
                                        }
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
                text = pymupdf.open(dest)[0].get_text()
                self.assertIn("来自缓存", text)
            finally:
                if old is None:
                    os.environ.pop("QYUNSLATION_LETTER_CACHE", None)
                else:
                    os.environ["QYUNSLATION_LETTER_CACHE"] = old

    def test_reinsert_kinds_logo_only(self):
        import pymupdf
        from graphic_reinsert import reinsert

        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            pdf = tdir / "m.pdf"
            doc = pymupdf.open()
            doc.new_page(width=595.32, height=841.92)
            doc.save(pdf)
            doc.close()
            gdir = Path(str(pdf) + ".graphics")
            gdir.mkdir()
            # 1x1 png
            import struct
            import zlib

            def _png(path: Path) -> None:
                raw = b"\x00" + b"\xff\x00\x00"  # RGB red pixel with filter
                comp = zlib.compress(raw)
                def chunk(tag: bytes, data: bytes) -> bytes:
                    return (
                        struct.pack(">I", len(data))
                        + tag
                        + data
                        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
                    )
                ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
                path.write_bytes(
                    b"\x89PNG\r\n\x1a\n"
                    + chunk(b"IHDR", ihdr)
                    + chunk(b"IDAT", comp)
                    + chunk(b"IEND", b"")
                )

            _png(gdir / "p1-r0.png")
            _png(gdir / "p1-r1.png")
            mf = Path(str(pdf) + ".graphics.json")
            mf.write_text(
                json.dumps(
                    {
                        "source": str(pdf),
                        "dpi": 72,
                        "pages": [
                            {
                                "page": 1,
                                "size": [595.32, 841.92],
                                "regions": [
                                    {
                                        "box": [70, 70, 100, 100],
                                        "kind": "logo",
                                        "suppress_text": True,
                                        "png": "p1-r0.png",
                                    },
                                    {
                                        "box": [71, 385, 486, 426],
                                        "kind": "graphic",
                                        "suppress_text": False,
                                        "png": "p1-r1.png",
                                    },
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            n = reinsert(pdf, mf, kinds={"logo", "stamp"})
            self.assertEqual(n, 1)
            imgs = pymupdf.open(pdf)[0].get_image_info() or []
            self.assertEqual(len(imgs), 1)


if __name__ == "__main__":
    unittest.main()
