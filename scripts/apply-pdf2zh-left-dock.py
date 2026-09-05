#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-019：左栏翻译/取消 + 高级选项 sticky 吸底。

须在 apply-pdf2zh-adv-options.py 之后执行。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)

CSS_MARKER = "/* _qy_left_dock_css */"
JS_MARKER = "_qy_left_dock_js"

CSS_BLOCK = """
    /* _qy_left_dock_css */
    .qy-col-left {
        --qy-dock-h: 58px;
    }
    .qy-col-left > .action-row {
        position: sticky !important;
        bottom: var(--qy-dock-h, 58px) !important;
        z-index: 30 !important;
        background: #fff !important;
        border-top: 1px solid #e2e8f0 !important;
        padding-top: 8px !important;
        padding-bottom: 4px !important;
        margin-top: 8px !important;
        box-shadow: 0 -4px 12px rgba(15, 23, 42, 0.04) !important;
    }
    .qy-col-left > .qy-adv-acc {
        position: sticky !important;
        bottom: 0 !important;
        z-index: 31 !important;
        background: #fff !important;
        margin-top: 0 !important;
        box-shadow: 0 -2px 8px rgba(15, 23, 42, 0.03) !important;
    }
    .qy-col-left > .qy-adv-acc > :last-child {
        max-height: min(38vh, 340px) !important;
        overflow-y: auto !important;
    }
    .qy-col-left:has(.qy-adv-acc .label-wrap.open) > .action-row {
        bottom: calc(58px + min(38vh, 340px)) !important;
    }
"""

DOCK_JS_SNIPPET = """
  function qyUpdateDockHeight() {
    var left = document.querySelector('.qy-col-left');
    var acc = document.querySelector('.qy-adv-acc');
    if (!left || !acc) return;
    var h = Math.ceil(acc.getBoundingClientRect().height) || 58;
    left.style.setProperty('--qy-dock-h', h + 'px');
  }
  qyUpdateDockHeight();
  setInterval(qyUpdateDockHeight, 400);
  if (document.body) {
    new MutationObserver(qyUpdateDockHeight).observe(document.body, {
      childList: true, subtree: true, attributes: true, attributeFilter: ['class']
    });
  }
"""


def _custom_css_span(text: str) -> tuple[int, int] | None:
    start = text.find('custom_css = """')
    if start < 0:
        return None
    content_start = start + len('custom_css = """')
    m = re.search(r"\n[ \t]*\"\"\"", text[content_start:])
    if not m:
        return None
    return content_start, content_start + m.start()


def apply_css(text: str) -> tuple[str, bool]:
    desired = "\n" + CSS_BLOCK.rstrip() + "\n"
    span = _custom_css_span(text)
    if not span:
        print("WARNING: custom_css span missing", file=sys.stderr)
        return text, False
    c0, c1 = span
    css_body = text[c0:c1]
    adv_i = css_body.find("/* _qy_adv_options_css */")
    dock_i = css_body.find(CSS_MARKER)
    if (
        adv_i >= 0
        and dock_i > adv_i
        and text.count(CSS_MARKER) == 1
        and desired.strip() in css_body
    ):
        return text, False

    # Strip any existing dock blocks then append after current CSS end
    if CSS_MARKER in text:
        pat = re.compile(
            r"\n[ \t]*/\* _qy_left_dock_css \*/\n"
            r"(?:[ \t]*[^\n]+\n)*?"
            r"[ \t]*\.qy-col-left:has\(\.qy-adv-acc \.label-wrap\.open\) > \.action-row \{.*?\n[ \t]*\}\n",
            re.S,
        )
        text2, n = pat.subn("\n", text)
        if n:
            text = text2
        span = _custom_css_span(text)
        if not span:
            print("WARNING: custom_css missing after strip", file=sys.stderr)
            return text, True
        c0, c1 = span
        css_body = text[c0:c1]

    if "/* _qy_adv_options_css */" not in css_body:
        print("WARNING: adv options css missing; inserting dock at end", file=sys.stderr)
    new_body = css_body.rstrip() + desired
    return text[:c0] + new_body + text[c1:], True


def apply_js(text: str) -> tuple[str, bool]:
    """Inject dock height updater into existing Blocks(js=...) page-sync function."""
    if JS_MARKER in text:
        return text, False
    # Prefer inject before closing of page sync arrow function
    # Look for `__qyPageSyncInstalled` block's trailing `}`
    marker = "window.__qyPageSyncInstalled"
    if marker not in text:
        print("WARNING: page sync js missing; skip dock js", file=sys.stderr)
        return text, False
    # Insert before the final `}` of the arrow function that starts with () => {
    # Find js="""...""" after _qy_page_sync_blocks
    m = re.search(
        r'(# _qy_page_sync_blocks\n    js=""")(.*?)(""",\n\) as demo:)',
        text,
        re.S,
    )
    if not m:
        print("WARNING: Blocks js region missing", file=sys.stderr)
        return text, False
    body = m.group(2)
    if JS_MARKER in body:
        return text, False
    # Append before the last closing brace of the outer arrow fn
    # body is like: () => {\n ... \n}\n
    insert = "\n  // " + JS_MARKER + "\n" + DOCK_JS_SNIPPET
    # Find last `}` that closes the arrow function
    last_brace = body.rfind("}")
    if last_brace < 0:
        return text, False
    new_body = body[:last_brace] + insert + "\n" + body[last_brace:]
    text2 = text[: m.start(2)] + new_body + text[m.end(2) :]
    return text2, True


def apply(text: str) -> tuple[str, bool]:
    changed = False
    for fn in (apply_css, apply_js):
        text, c = fn(text)
        changed = changed or c
    return text, changed


def verify(text: str) -> int:
    errs = 0

    def need(cond: bool, msg: str) -> None:
        nonlocal errs
        if not cond:
            print(f"ERROR: {msg}", file=sys.stderr)
            errs += 1

    span = _custom_css_span(text)
    need(span is not None, "custom_css missing")
    if span:
        css = text[span[0] : span[1]]
        need(CSS_MARKER in css, "left dock css not in custom_css")
        need("/* _qy_adv_options_css */" in css, "adv css missing")
        adv_i = css.find("/* _qy_adv_options_css */")
        dock_i = css.find(CSS_MARKER)
        need(dock_i > adv_i, "dock css must follow adv css")
        need("position: sticky" in css[dock_i:], "sticky rule missing")
    need(JS_MARKER in text or CSS_MARKER in text, "dock js or css missing")
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
    final = GUI.read_text(encoding="utf-8") if changed else original
    errs = verify(final)
    if errs:
        print(f"verify failed: {errs} error(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
