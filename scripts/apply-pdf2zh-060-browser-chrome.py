#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Patch browser-facing Gradio callback quirks in the installed pdf2zh GUI."""

from __future__ import annotations

import argparse
import py_compile
from pathlib import Path


GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/"
    "pdf2zh_next/gui.py"
)

ANCHOR = "# JavaScript: 动态调整 PDF canvas 缩放，确保完全适配容器高度"
MARKER = "# PLAN-060: canvas load callback must be a Gradio function"
BAD_START = "            (function() {"
GOOD_START = "            () => {"
BAD_END = "            })();\n            \"\"\"\n        )"
GOOD_END = "            }\n            \"\"\"\n        )"


def apply(source: str) -> tuple[str, bool]:
    """Convert the target demo.load js IIFE into a parseable Gradio function."""
    anchor_at = source.find(ANCHOR)
    if anchor_at < 0:
        return source, False

    head = source[:anchor_at]
    tail = source[anchor_at:]
    if MARKER in tail:
        return source, False

    start_at = tail.find(BAD_START)
    if start_at < 0:
        return source, False
    end_at = tail.find(BAD_END, start_at)
    if end_at < 0:
        return source, False

    block = tail[start_at:end_at].replace(BAD_START, GOOD_START, 1)
    suffix = tail[end_at:].replace(BAD_END, GOOD_END, 1)
    patched_tail = (
        tail[:start_at]
        + f"            {MARKER}\n"
        + block
        + suffix
    )
    return head + patched_tail, True


def verify(path: Path = GUI) -> bool:
    if not path.exists():
        print(f"BLOCKED: GUI source not found: {path}")
        return False
    text = path.read_text(encoding="utf-8")
    anchor_at = text.find(ANCHOR)
    if anchor_at < 0:
        print("FAIL: canvas callback anchor missing")
        return False
    tail = text[anchor_at:]
    if MARKER not in tail:
        print("FAIL: PLAN-060 browser callback marker missing")
        return False
    marker_tail = tail[tail.find(MARKER) :]
    if BAD_START in marker_tail or BAD_END in marker_tail:
        print("FAIL: canvas load callback still uses an IIFE")
        return False
    try:
        py_compile.compile(str(path), doraise=True)
    except py_compile.PyCompileError as exc:
        print(f"FAIL: patched GUI does not compile: {exc.msg}")
        return False
    print("PASS: PLAN-060 browser callback patch is present")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--path", type=Path, default=GUI)
    args = parser.parse_args()

    if args.verify:
        return 0 if verify(args.path) else 2
    if not args.path.exists():
        print(f"BLOCKED: GUI source not found: {args.path}")
        return 2

    source = args.path.read_text(encoding="utf-8")
    patched, changed = apply(source)
    if changed:
        args.path.write_text(patched, encoding="utf-8")
        print("patched: PLAN-060 browser callback")
    else:
        print("unchanged: PLAN-060 browser callback")
    return 0 if verify(args.path) else 2


if __name__ == "__main__":
    raise SystemExit(main())
