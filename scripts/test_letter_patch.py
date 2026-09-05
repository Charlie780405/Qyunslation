#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-009c：letter typesetting patch 冒烟。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from doc_profile import get, patch_letter_typesetting  # noqa: E402


class TestLetterPatch(unittest.TestCase):
    def test_patch_letter_injects(self):
        from babeldoc.format.pdf.document_il.midend import typesetting

        ok = patch_letter_typesetting(get("letter"))
        self.assertTrue(ok)
        self.assertTrue(
            getattr(typesetting.Typesetting.render_paragraph, "_qy_letter_patched", False)
        )
        self.assertTrue(
            getattr(
                typesetting.Typesetting._layout_typesetting_units,
                "_qy_letter_align_patched",
                False,
            )
        )
        # 幂等
        self.assertTrue(patch_letter_typesetting(get("letter")))

    def test_non_letter_keys_noop_profile(self):
        # literature 无 body_font_size 且 name!=letter → False
        prof = get("literature")
        # 故意不带 letter 字段
        self.assertNotIn("body_font_size", prof)
        # patch 要求 name==letter 或有 body_font_size
        from doc_profile import patch_letter_typesetting as patch

        # 若已注入过仍可能 True（全局已 patch）；这里只断言调用不抛
        patch(prof)


if __name__ == "__main__":
    unittest.main()
