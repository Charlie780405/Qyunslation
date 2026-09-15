#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Patch browser-facing Gradio callback quirks in the installed pdf2zh GUI."""

from __future__ import annotations

import argparse
import py_compile
import shutil
from pathlib import Path


GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/"
    "pdf2zh_next/gui.py"
)
GRADIO_FONT_ROOT = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/"
    "gradio/templates/frontend/static/fonts"
)

ANCHOR = "# JavaScript: 动态调整 PDF canvas 缩放，确保完全适配容器高度"
MARKER = "# PLAN-060: canvas load callback must be a Gradio function"
LEGACY_MARKER = "_qy_060_canvas_load_fn"
BAD_START = "            (function() {"
GOOD_START = "            () => {"
BAD_END = "            })();\n            \"\"\"\n        )"
GOOD_END = "            }\n            \"\"\"\n        )"
FONT_ALIASES = (
    ("IBMPlexSans", "IBMPlexSans-Regular.woff2", "ui-sans-serif", "ui-sans-serif-Regular.woff2"),
    ("IBMPlexSans", "IBMPlexSans-Bold.woff2", "ui-sans-serif", "ui-sans-serif-Bold.woff2"),
    ("IBMPlexSans", "IBMPlexSans-Regular.woff2", "system-ui", "system-ui-Regular.woff2"),
    ("IBMPlexSans", "IBMPlexSans-Bold.woff2", "system-ui", "system-ui-Bold.woff2"),
    ("IBMPlexMono", "IBMPlexMono-Regular.woff2", "ui-monospace", "ui-monospace-Regular.woff2"),
    ("IBMPlexMono", "IBMPlexMono-Bold.woff2", "ui-monospace", "ui-monospace-Bold.woff2"),
    ("IBMPlexMono", "IBMPlexMono-Regular.woff2", "Consolas", "Consolas-Regular.woff2"),
    ("IBMPlexMono", "IBMPlexMono-Bold.woff2", "Consolas", "Consolas-Bold.woff2"),
)


def apply(source: str) -> tuple[str, bool]:
    """Convert the target demo.load js IIFE into a parseable Gradio function."""
    anchor_at = source.find(ANCHOR)
    if anchor_at < 0:
        return source, False

    head = source[:anchor_at]
    tail = source[anchor_at:]
    if MARKER in tail or LEGACY_MARKER in tail:
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


def ensure_font_aliases(font_root: Path = GRADIO_FONT_ROOT) -> tuple[int, list[str]]:
    """Create local font aliases requested by Gradio's generated CSS."""
    created = 0
    warnings: list[str] = []
    for src_family, src_name, dst_family, dst_name in FONT_ALIASES:
        source = font_root / src_family / src_name
        target = font_root / dst_family / dst_name
        if target.is_file():
            continue
        if not source.is_file():
            warnings.append(f"missing font source: {source}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        created += 1
    return created, warnings


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
    if MARKER not in tail and LEGACY_MARKER not in tail:
        print("FAIL: PLAN-060 browser callback marker missing")
        return False
    marker_at = tail.find(MARKER)
    legacy_at = tail.find(LEGACY_MARKER)
    marker_candidates = [pos for pos in (marker_at, legacy_at) if pos >= 0]
    marker_tail = tail[min(marker_candidates) :]
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
    created, warnings = ensure_font_aliases()
    if created:
        print(f"patched: PLAN-060 browser font aliases={created}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    return 0 if verify(args.path) else 2


if __name__ == "__main__":
    raise SystemExit(main())
