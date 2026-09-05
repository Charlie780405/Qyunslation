#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-017b：进度条迁左栏 + 当前文档下拉迁左栏 + 双框等高 + 页脚细条。

须在 apply-pdf2zh-dual-preview.py 之后执行。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)

MARKER = "# _qy_layout_polish"
CSS_MARKER = "/* _qy_layout_polish_css */"

SELECTOR_BLOCK = '''                            result_file_selector = gr.Dropdown(
                                label="当前文档",
                                choices=[],
                                value=None,
                                visible=True,
                                interactive=True,
                            )
'''

PROGRESS_BLOCK = '''                            qy_progress_slot = gr.HTML(
                                value="",
                                visible=True,
                                elem_classes=["qy-progress-slot"],
                            )
'''

CSS_BLOCK = """
    /* _qy_layout_polish_css */
    /* neutralize PLAN-017 right-column progress order */
    .qy-progress-slot {
        order: unset !important;
        flex: 0 0 auto !important;
    }
    /* leave room for inline footer sibling inside tab_main */
    :root { --qy-shell-top: 120px !important; }
    .tab-main-row {
        height: calc(100vh - 128px) !important;
        max-height: calc(100vh - 128px) !important;
    }
    .qy-main-inner-row {
        flex: 1 1 0 !important;
        height: auto !important;
        max-height: none !important;
        min-height: 0 !important;
        padding-bottom: 0 !important;
    }
    .qy-col-left > .qy-progress-slot {
        display: none !important;
        flex: 0 0 0 !important;
        height: 0 !important;
        min-height: 0 !important;
        max-height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        border: none !important;
        overflow: hidden !important;
        order: unset !important;
    }
    .qy-col-left > .qy-progress-slot:has(> .wrap:not(.hide)) {
        display: block !important;
        position: relative !important;
        flex: 0 0 auto !important;
        height: auto !important;
        min-height: 44px !important;
        max-height: none !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 8px !important;
        background: #f8fafc !important;
        overflow: hidden !important;
        margin: 0 !important;
        padding: 0 !important;
        order: unset !important;
    }
    .qy-col-left > .qy-progress-slot:has(> .wrap:not(.hide)) .wrap {
        position: relative !important;
        inset: auto !important;
        padding: 8px 10px !important;
    }
    .qy-col-mid,
    .qy-col-right {
        height: 100% !important;
        min-height: 0 !important;
        display: flex !important;
        flex-direction: column !important;
        gap: 8px !important;
    }
    .qy-col-mid > *,
    .qy-col-right > * {
        flex: 0 0 auto !important;
    }
    .qy-col-mid > .pdf-preview-fixed.hidden,
    .qy-col-mid > .qy-html-preview-wrap.hidden,
    .qy-col-right > .pdf-preview-fixed.hidden,
    .qy-col-right > .qy-html-preview-wrap.hidden {
        display: none !important;
        flex: 0 0 0 !important;
        height: 0 !important;
        max-height: 0 !important;
        min-height: 0 !important;
        overflow: hidden !important;
        border: none !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    .qy-col-mid > .pdf-preview-fixed:not(.hidden):has(canvas),
    .qy-col-mid > .pdf-preview-fixed:not(.hidden):has(iframe),
    .qy-col-mid > .pdf-preview-fixed:not(.hidden):has(embed),
    .qy-col-mid > .qy-html-preview-wrap:not(.hidden),
    .qy-col-right > .pdf-preview-fixed:not(.hidden):has(canvas),
    .qy-col-right > .pdf-preview-fixed:not(.hidden):has(iframe),
    .qy-col-right > .pdf-preview-fixed:not(.hidden):has(embed),
    .qy-col-right > .qy-html-preview-wrap:not(.hidden) {
        flex: 1 1 auto !important;
        min-height: 0 !important;
        height: auto !important;
        max-height: none !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 10px !important;
        overflow: auto !important;
        order: unset !important;
    }
    .qy-col-mid::after,
    .qy-col-right::after {
        content: "上传文件后在此预览原文";
        flex: 1 1 auto;
        display: flex;
        align-items: center;
        justify-content: center;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        background: transparent;
        color: #94a3b8;
        font-size: 0.95rem;
        min-height: 120px;
        order: unset !important;
    }
    .qy-col-right::after {
        content: "翻译完成后在此显示译文" !important;
    }
    .qy-col-mid:has(> .pdf-preview-fixed:not(.hidden):has(canvas))::after,
    .qy-col-mid:has(> .pdf-preview-fixed:not(.hidden):has(iframe))::after,
    .qy-col-mid:has(> .pdf-preview-fixed:not(.hidden):has(embed))::after,
    .qy-col-mid:has(> .qy-html-preview-wrap:not(.hidden))::after,
    .qy-col-right:has(> .pdf-preview-fixed:not(.hidden):has(canvas))::after,
    .qy-col-right:has(> .pdf-preview-fixed:not(.hidden):has(iframe))::after,
    .qy-col-right:has(> .pdf-preview-fixed:not(.hidden):has(embed))::after,
    .qy-col-right:has(> .qy-html-preview-wrap:not(.hidden))::after {
        display: none !important;
    }
    .qy-inline-footer-row {
        flex: 0 0 auto !important;
        gap: 20px !important;
        min-height: 34px !important;
        max-height: 40px !important;
        margin-top: 4px !important;
        align-items: center !important;
        padding: 0 20px 4px 4px !important;
    }
    .qy-footer-spacer {
        min-height: 0 !important;
        visibility: hidden !important;
        pointer-events: none !important;
    }
    .qy-inline-footer-col {
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        min-height: 0 !important;
        margin-left: -4px !important;
    }
    .qy-inline-footer {
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 8px !important;
        width: 100% !important;
        height: 34px !important;
        color: #94a3b8 !important;
        font-size: 0.8rem !important;
        border: 1px solid #eef2f7 !important;
        border-radius: 8px !important;
        background: #fafbfc !important;
        padding: 0 12px !important;
        box-sizing: border-box !important;
    }
    .qy-inline-footer img {
        height: 16px !important;
        width: auto !important;
        max-width: 120px !important;
        object-fit: contain !important;
    }
"""


def _left_span(text: str) -> tuple[int, int] | None:
    left = text.find('elem_classes=["qy-col-left"]')
    mid = text.find('elem_classes=["qy-col-mid"]')
    if left < 0 or mid < 0 or mid <= left:
        return None
    return left, mid


def _line_start(text: str, idx: int) -> int:
    """Return index of the first character of the line containing idx."""
    if idx <= 0:
        return 0
    nl = text.rfind("\n", 0, idx)
    return 0 if nl < 0 else nl + 1


def apply_move_selector(text: str) -> tuple[str, bool]:
    span = _left_span(text)
    if not span:
        print("WARNING: left/mid anchors missing", file=sys.stderr)
        return text, False
    left, mid = span
    left_body = text[left:mid]
    if "result_file_selector = gr.Dropdown" in left_body:
        return text, False
    if SELECTOR_BLOCK not in text:
        print("WARNING: selector block missing", file=sys.stderr)
        return text, False
    text = text.replace(SELECTOR_BLOCK, "", 1)
    span = _left_span(text)
    if not span:
        return text, False
    left, mid = span
    title = text.find('gr.Markdown(_("## Translation Options")', left, mid)
    if title < 0:
        print("WARNING: Translation Options anchor missing in left", file=sys.stderr)
        return text, False
    insert_at = _line_start(text, title)
    # Prefer after uploaded_files_view closing if it sits before Translation Options
    uf = text.find("uploaded_files_view = gr.Markdown(", left, mid)
    if uf >= 0 and uf < insert_at:
        # find the assignment's closing paren at same indent
        close = text.find("\n                            )\n", uf, insert_at)
        if close >= 0:
            insert_at = close + len("\n                            )\n")
            if text[insert_at : insert_at + 1] == "\n":
                insert_at += 1
    marker_line = f"                            {MARKER}: selector\n"
    text = text[:insert_at] + marker_line + SELECTOR_BLOCK + text[insert_at:]
    return text, True


def apply_move_progress(text: str) -> tuple[str, bool]:
    span = _left_span(text)
    if not span:
        print("WARNING: left/mid anchors missing", file=sys.stderr)
        return text, False
    left, mid = span
    left_body = text[left:mid]
    if "qy_progress_slot = gr.HTML" in left_body:
        return text, False
    if PROGRESS_BLOCK not in text:
        print("WARNING: progress block missing", file=sys.stderr)
        return text, False
    text = text.replace(PROGRESS_BLOCK, "", 1)
    span = _left_span(text)
    if not span:
        return text, False
    left, mid = span
    title = text.find('gr.Markdown(_("## Translation Options")', left, mid)
    if title < 0:
        print("WARNING: Translation Options for progress missing", file=sys.stderr)
        return text, False
    insert_at = _line_start(text, title)
    marker_line = f"                            {MARKER}: progress\n"
    text = text[:insert_at] + marker_line + PROGRESS_BLOCK + "\n" + text[insert_at:]
    return text, True


def apply_css(text: str) -> tuple[str, bool]:
    original = text
    while CSS_MARKER in text:
        m = re.search(
            r"\n    /\* _qy_layout_polish_css \*/.*?\.qy-inline-footer img \{.*?\n    \}\n",
            text,
            re.S,
        )
        if m:
            text = text[: m.start()] + "\n" + text[m.end() :]
            continue
        start = text.find("    /* _qy_layout_polish_css */")
        if start < 0:
            break
        stop = text.find('\n    """', start)
        if stop < 0:
            stop = text.find("\n\"\"\"", start)
        if stop < 0:
            break
        text = text[:start] + text[stop:]

    anchor = '\n    """\n\n# Build paths to resources'
    if anchor not in text:
        print("WARNING: CSS inject point missing", file=sys.stderr)
        return text, text != original
    idx = text.find(anchor)
    text = text[:idx].rstrip() + "\n" + CSS_BLOCK + text[idx:]
    return text, text != original


PAGE_SYNC_JS = r"""
() => {
  if (window.__qyPageSyncInstalled) return;
  window.__qyPageSyncInstalled = true;
  var syncingPage = false;
  var syncingScroll = false;

  function pageInput(root) {
    return root ? root.querySelector('.page-count input[type="number"]') : null;
  }

  function setPage(input, page) {
    if (!input) return;
    var max = parseInt(input.max || '9999', 10) || 9999;
    var min = parseInt(input.min || '1', 10) || 1;
    var p = Math.min(max, Math.max(min, page | 0));
    if (String(input.value) === String(p)) return;
    input.value = String(p);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function syncPageFromTo(fromRoot, toRoot) {
    if (syncingPage) return;
    var fi = pageInput(fromRoot), ti = pageInput(toRoot);
    if (!fi || !ti) return;
    syncingPage = true;
    try { setPage(ti, parseInt(fi.value, 10) || 1); }
    finally { syncingPage = false; }
  }

  function bindPagePair(aRoot, bRoot) {
    if (!aRoot || !bRoot) return;
    if (aRoot.__qyPageBound && bRoot.__qyPageBound) return;
    aRoot.__qyPageBound = true;
    bRoot.__qyPageBound = true;

    function onEvt(from, to, e) {
      var t = e.target;
      if (t && t.matches && t.matches('.page-count input[type="number"]')) {
        syncPageFromTo(from, to);
      }
    }
    function onClick(from, to, e) {
      var el = e.target;
      if (el && el.closest && el.closest('.button-row')) {
        setTimeout(function () { syncPageFromTo(from, to); }, 30);
      }
    }
    aRoot.addEventListener('input', function (e) { onEvt(aRoot, bRoot, e); }, true);
    aRoot.addEventListener('change', function (e) { onEvt(aRoot, bRoot, e); }, true);
    aRoot.addEventListener('click', function (e) { onClick(aRoot, bRoot, e); }, true);
    bRoot.addEventListener('input', function (e) { onEvt(bRoot, aRoot, e); }, true);
    bRoot.addEventListener('change', function (e) { onEvt(bRoot, aRoot, e); }, true);
    bRoot.addEventListener('click', function (e) { onClick(bRoot, aRoot, e); }, true);
  }

  function scrollableOf(root) {
    if (!root) return null;
    if (root.scrollHeight > root.clientHeight + 2) return root;
    var kids = root.querySelectorAll('.html-container, .prose, .wrap');
    for (var i = 0; i < kids.length; i++) {
      if (kids[i].scrollHeight > kids[i].clientHeight + 2) return kids[i];
    }
    return root;
  }

  function bindScrollPair(aRoot, bRoot) {
    if (!aRoot || !bRoot) return;
    var a = scrollableOf(aRoot);
    var b = scrollableOf(bRoot);
    if (!a || !b) return;
    if (a.__qyScrollBound && b.__qyScrollBound) return;
    a.__qyScrollBound = true;
    b.__qyScrollBound = true;
    function mirror(src, dst) {
      if (syncingScroll) return;
      var maxS = src.scrollHeight - src.clientHeight;
      var maxD = dst.scrollHeight - dst.clientHeight;
      if (maxS <= 0 || maxD <= 0) return;
      syncingScroll = true;
      try { dst.scrollTop = (src.scrollTop / maxS) * maxD; }
      finally { syncingScroll = false; }
    }
    a.addEventListener('scroll', function () { mirror(a, b); }, { passive: true });
    b.addEventListener('scroll', function () { mirror(b, a); }, { passive: true });
  }

  function tick() {
    var src = document.querySelector('.qy-preview-src:not(.hidden)');
    var dst = document.querySelector('.qy-preview-dst:not(.hidden)');
    if (src && dst) {
      bindPagePair(src, dst);
      bindScrollPair(src, dst);
    }
    var srcH = document.querySelector('.qy-preview-src-html:not(.hidden)');
    var dstH = document.querySelector('.qy-preview-dst-html:not(.hidden)');
    if (srcH && dstH) bindScrollPair(srcH, dstH);
  }

  tick();
  setInterval(tick, 1000);
  if (document.body) {
    new MutationObserver(tick).observe(document.body, { childList: true, subtree: true });
  }
}
"""


def apply_page_sync(text: str) -> tuple[str, bool]:
    """Inject page/scroll sync via Blocks(js=...) as a single function (Gradio requirement)."""
    changed = False

    # Remove previous demo.load injection if present
    if "// _qy_page_sync:" in text:
        pat2 = re.compile(
            r"\n            // _qy_page_sync:[^\n]*\n            \(function setupQyPageSync\(\) \{.*?\n            \}\)\(\);\n",
            re.S,
        )
        text2, n2 = pat2.subn("\n", text, count=1)
        if n2:
            text = text2
            changed = True

    # Refresh Blocks js if marker present but body outdated (not arrow function)
    if "_qy_page_sync_blocks" in text:
        # Replace existing js="""...""" after the marker
        pat = re.compile(
            r'(# _qy_page_sync_blocks\n    js=""")(.*?)(""",\n\) as demo:)',
            re.S,
        )
        m = pat.search(text)
        if m:
            new_block = m.group(1) + PAGE_SYNC_JS + m.group(3)
            if m.group(0) != new_block:
                text = text[: m.start()] + new_block + text[m.end() :]
                return text, True
            return text, changed
        return text, changed

    old = "    css=custom_css,\n) as demo:"
    new = (
        "    css=custom_css,\n"
        '    # _qy_page_sync_blocks\n'
        '    js="""' + PAGE_SYNC_JS + '""",\n'
        ") as demo:"
    )
    if old not in text:
        print("WARNING: Blocks css=custom_css anchor missing", file=sys.stderr)
        return text, changed
    text = text.replace(old, new, 1)
    return text, True


def apply(text: str) -> tuple[str, bool]:
    changed = False
    for fn in (apply_move_selector, apply_move_progress, apply_css, apply_page_sync):
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

    span = _left_span(text)
    need(span is not None, "left/mid span missing")
    if span:
        left, mid = span
        left_body = text[left:mid]
        need(
            left_body.count("result_file_selector = gr.Dropdown") == 1,
            "selector not uniquely in left column",
        )
        need(
            left_body.count("qy_progress_slot = gr.HTML") == 1,
            "progress slot not uniquely in left column",
        )
        # progress should appear after selector and before Translation Options
        sel_i = left_body.find("result_file_selector = gr.Dropdown")
        prog_i = left_body.find("qy_progress_slot = gr.HTML")
        title_i = left_body.find('gr.Markdown(_("## Translation Options")')
        need(sel_i >= 0 and prog_i > sel_i, "selector before progress")
        need(prog_i >= 0 and title_i > prog_i, "progress before Translation Options")
    need(text.count("result_file_selector = gr.Dropdown") == 1, "selector defs != 1")
    need(text.count("qy_progress_slot = gr.HTML") == 1, "progress defs != 1")
    need(CSS_MARKER in text, "polish css missing")
    dual_i = text.find("/* _qy_dual_preview_css */")
    polish_i = text.find(CSS_MARKER)
    need(dual_i >= 0 and polish_i > dual_i, "polish css must follow dual css")
    need("show_progress_on=[qy_progress_slot]" in text, "progress bind missing")
    need("_qy_page_sync_blocks" in text or "_qy_page_sync" in text, "page sync js missing")
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
