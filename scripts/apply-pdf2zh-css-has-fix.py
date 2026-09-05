#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-020：修复嵌套 :has() 导致空态提示无法隐藏。

`:has()` 内部不允许再出现 `:has()`。选择器组里只要有一个成员非法，
整条规则会被浏览器整体丢弃，于是「上传文件后在此预览原文 / 翻译完成后在此
显示译文」的隐藏规则从未生效——预览已经渲染，下方还挂着一个空框。

把 `:has(> .pdf-preview-fixed:not(.hidden):has(canvas))`
改写为 `:has(> .pdf-preview-fixed:not(.hidden) canvas)`（后代组合器，合法）。

须在所有产出该选择器的 CSS 补丁之后执行。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)

NESTED_RE = re.compile(
    r":has\((>\s*\.pdf-preview-fixed:not\(\.hidden\)):has\((canvas|iframe|embed)\)\)"
)


def apply(text: str) -> tuple[str, bool]:
    new = NESTED_RE.sub(r":has(\1 \2)", text)
    return new, new != text


def verify(text: str) -> int:
    errs = 0

    def need(cond: bool, msg: str) -> None:
        nonlocal errs
        if not cond:
            print(f"ERROR: {msg}", file=sys.stderr)
            errs += 1

    need(not NESTED_RE.search(text), "nested :has() still present")
    need(
        ":has(> .pdf-preview-fixed:not(.hidden) canvas)" in text,
        "rewritten descendant selector missing",
    )
    # 仍应保留 :not(:has(...)) 这类合法写法
    need(
        ".pdf-preview-fixed:not(:has(canvas))" in text,
        ":not(:has()) form was clobbered",
    )
    try:
        compile(text, str(GUI), "exec")
    except SyntaxError as e:
        print(f"ERROR: syntax: {e}", file=sys.stderr)
        errs += 1
    return errs


def main() -> int:
    if not GUI.is_file():
        print(f"ERROR: missing {GUI}", file=sys.stderr)
        return 1
    original = GUI.read_text(encoding="utf-8")
    updated, changed = apply(original)
    if changed:
        GUI.write_text(updated, encoding="utf-8")
        print("patched:", GUI)
    else:
        print("already patched:", GUI)
    errs = verify(updated if changed else original)
    if errs:
        print(f"verify failed: {errs} error(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
