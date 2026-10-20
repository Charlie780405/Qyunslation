# SPDX-License-Identifier: MPL-2.0
"""PLAN-080c：apply-pdf2zh-080c-fonts.py 的补丁文本契约（只在内存中验证，不触碰 site-packages）。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("apply_080c", ROOT / "scripts" / "apply-pdf2zh-080c-fonts.py")
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)

SOURCE = "import os\n\n\nclass FontMapper:\n    def map(self, original_font, char_unicode):\n        return None\n"


def test_appends_marked_block_once():
    new, changed = patch.patch_fontmap(SOURCE)
    assert changed and patch.MARKER in new
    assert "install as _qy_080c_install" in new
    again, changed_again = patch.patch_fontmap(new)
    assert not changed_again and again == new


def test_patched_module_still_compiles_and_survives_missing_policy():
    new, _ = patch.patch_fontmap(SOURCE)
    namespace: dict = {}
    exec(compile(new, "fontmap_patched.py", "exec"), namespace)  # noqa: S102
    assert namespace["FontMapper"]().map(None, "a") is None


def test_unrelated_file_is_left_alone():
    text = "print('not a font mapper')\n"
    assert patch.patch_fontmap(text) == (text, False)


def test_block_is_registered_in_the_patch_chain():
    assert "apply-pdf2zh-080c-fonts.py" in (ROOT / "scripts" / "pdf2zh.service").read_text(encoding="utf-8")
    assert "apply-pdf2zh-080c-fonts.py" in (ROOT / "docs" / "contracts" / "pdf2zh-patch-order.md").read_text(encoding="utf-8")
