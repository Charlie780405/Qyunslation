#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-033e：当前页预览 300 DPI 标记 + 懒加载钩子。

须在 apply-pdf2zh-viewer.py 之后执行。
"""
from __future__ import annotations

import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)
MARKER = "_qy_preview_dpi"
ANCHOR = "  // _qy_viewer_js_end\n"

JS = r"""
  // _qy_preview_dpi
  (function () {
    if (window.__qyPreviewDpiInstalled) return;
    window.__qyPreviewDpiInstalled = true;
    window.__qyPreviewHiDpi = 300;
    window.__qyPreviewLoDpi = 72;
    window.__qyPreviewCurrentPage = 1;
    function currentPage() {
      var input = document.querySelector('.qy-preview-dst .page-count input[type="number"]')
        || document.querySelector('.page-count input[type="number"]');
      return input ? (parseInt(input.value, 10) || 1) : 1;
    }
    function dpiFor(page) {
      return page === window.__qyPreviewCurrentPage
        ? window.__qyPreviewHiDpi
        : window.__qyPreviewLoDpi;
    }
    function sync() {
      window.__qyPreviewCurrentPage = currentPage();
      document.documentElement.setAttribute(
        'data-qy-preview-page',
        String(window.__qyPreviewCurrentPage)
      );
      document.documentElement.setAttribute(
        'data-qy-preview-dpi',
        String(dpiFor(window.__qyPreviewCurrentPage))
      );
    }
    document.addEventListener('change', function (e) {
      if (e.target && e.target.matches && e.target.matches('.page-count input[type="number"]')) {
        sync();
      }
    }, true);
    document.addEventListener('input', function (e) {
      if (e.target && e.target.matches && e.target.matches('.page-count input[type="number"]')) {
        sync();
      }
    }, true);
    setInterval(sync, 1500);
    sync();
  })();
  // _qy_preview_dpi_end
"""


def apply(text: str) -> tuple[str, bool]:
    if MARKER in text:
        return text, False
    if ANCHOR in text:
        return text.replace(ANCHOR, ANCHOR + JS, 1), True
    fallback = "  window.__qyViewerInstalled = true;\n"
    if fallback in text:
        return text.replace(fallback, fallback + JS, 1), True
    return text, False


def verify(text: str) -> int:
    errs = 0

    def need(cond: bool, msg: str) -> None:
        nonlocal errs
        if not cond:
            print(f"ERROR: {msg}", file=sys.stderr)
            errs += 1

    need(MARKER in text, "preview dpi marker missing")
    need("__qyPreviewHiDpi = 300" in text, "300 DPI current-page hook missing")
    need("__qyPreviewLoDpi = 72" in text, "low-DPI placeholder hook missing")
    try:
        compile(text, str(GUI), "exec")
    except SyntaxError as e:
        print(f"ERROR: syntax {e}", file=sys.stderr)
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
    errs = verify(GUI.read_text(encoding="utf-8"))
    if errs:
        print(f"verify failed: {errs} error(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
