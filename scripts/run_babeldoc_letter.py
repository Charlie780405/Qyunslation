#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""CLI 入口：注入 letter 排版 patch 后转调 pdf2zh_next。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from doc_profile import get, patch_letter_typesetting, patch_line_skip  # noqa: E402
from letter_translate_prompt import system_prompt  # noqa: E402

prof = get("letter")
patch_line_skip(float(prof.get("line_skip") or 1.5))
patch_letter_typesetting(prof)

# 未显式给 --custom-system-prompt 时，注入跨页上下文提示
if "--custom-system-prompt" not in sys.argv:
    sys.argv[1:1] = ["--custom-system-prompt", system_prompt()]

from pdf2zh_next.main import cli  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(cli())
