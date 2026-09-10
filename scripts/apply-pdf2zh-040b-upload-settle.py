#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-040b：File Uploading 与 dual_payload/prescan 长链解耦。

- 首段 on_file_upload：正常进度
- dual_payload / prescan：show_progress=\"hidden\"，不挡文件框
- JS：upload POST 200 后若仍卡 Uploading，数秒后强制收起指示

须在 apply-pdf2zh-prescan.py 与 040a 之后跑。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)
MARKER = "PLAN-040b: upload settle"

OLD_CHAIN = '''        # _qy_upload_dual_then
        _qy_upload_evt = file_input.upload(
            on_file_upload,
            inputs=[file_input, state],
            outputs=[result_file_selector, state, uploaded_files_view],
        )
        _qy_upload_evt.then(
            _qy_dual_payload,
            inputs=[result_file_selector, state],
            outputs=[preview_src, preview_src_html, preview, preview_html],
        )
        # _qy_prescan
        _qy_upload_evt.then(
            _qy_prescan_tier1,
            inputs=[file_input, state, lang_to],
            outputs=[qy_prescan_status, state, qy_manifest_download],
        ).then(
            _qy_prescan_tier2,
            inputs=[file_input, state, lang_to],
            outputs=[qy_prescan_status, state, qy_manifest_download],
        ).then(
            _qy_prescan_tier3,
            inputs=[file_input, state],
            outputs=[qy_prescan_status, state, qy_manifest_download],
        )
'''

NEW_CHAIN = '''        # _qy_upload_dual_then
        # ''' + MARKER + '''
        _qy_upload_evt = file_input.upload(
            on_file_upload,
            inputs=[file_input, state],
            outputs=[result_file_selector, state, uploaded_files_view],
            show_progress="full",
        )
        _qy_upload_evt.then(
            _qy_dual_payload,
            inputs=[result_file_selector, state],
            outputs=[preview_src, preview_src_html, preview, preview_html],
            show_progress="hidden",
        )
        # _qy_prescan
        _qy_upload_evt.then(
            _qy_prescan_tier1,
            inputs=[file_input, state, lang_to],
            outputs=[qy_prescan_status, state, qy_manifest_download],
            show_progress="hidden",
        ).then(
            _qy_prescan_tier2,
            inputs=[file_input, state, lang_to],
            outputs=[qy_prescan_status, state, qy_manifest_download],
            show_progress="hidden",
        ).then(
            _qy_prescan_tier3,
            inputs=[file_input, state],
            outputs=[qy_prescan_status, state, qy_manifest_download],
            show_progress="hidden",
        )
'''

JS_MARKER = "_qy_upload_settle_js"
JS_BLOCK = r"""
  // _qy_upload_settle_js
  (function () {
    var settleTimer = null;
    function clearUploadingHints() {
      document.querySelectorAll('[data-testid="file"]').forEach(function (root) {
        root.querySelectorAll('*').forEach(function (el) {
          var t = (el.textContent || '').trim();
          if (/^Uploading\b/i.test(t) || /^正在上传/.test(t)) {
            var row = el.closest('div');
            if (row && row.style) row.style.display = 'none';
          }
        });
      });
    }
    var origFetch = window.fetch;
    if (!window.__qyUploadSettleWrapped) {
      window.__qyUploadSettleWrapped = true;
      window.fetch = function (input) {
        var url = String((input && input.url) || input || '');
        var p = origFetch.apply(this, arguments);
        if (url.indexOf('/gradio_api/upload') >= 0 || url.indexOf('/upload') >= 0) {
          p.then(function (r) {
            if (r && r.ok) {
              if (settleTimer) clearTimeout(settleTimer);
              settleTimer = setTimeout(clearUploadingHints, 2500);
            }
          }).catch(function () {});
        }
        return p;
      };
    }
  })();
  // _qy_upload_settle_js_end
"""


def patch_chain(text: str) -> tuple[str, bool]:
    if MARKER in text and 'show_progress="hidden"' in text:
        return text, False
    if OLD_CHAIN not in text:
        # maybe already partially patched — try looser match
        if (
            '_qy_upload_evt = file_input.upload(' in text
            and 'show_progress="hidden"' in text
            and MARKER in text
        ):
            return text, False
        print("WARNING: upload chain anchor missing", file=sys.stderr)
        return text, False
    return text.replace(OLD_CHAIN, NEW_CHAIN, 1), True


def patch_js(text: str) -> tuple[str, bool]:
    if JS_MARKER in text:
        return text, False
    anchor = "  window.__qyPageSyncInstalled = true;\n"
    if anchor not in text:
        # fall back after stale guard end
        end = "// _qy_stale_guard_js_end\n"
        if end in text:
            return text.replace(end, end + JS_BLOCK, 1), True
        print("WARNING: upload settle js anchor missing", file=sys.stderr)
        return text, False
    # Prefer after stale guard if present
    end = "// _qy_stale_guard_js_end\n"
    if end in text:
        return text.replace(end, end + JS_BLOCK, 1), True
    return text.replace(anchor, anchor + JS_BLOCK, 1), True


def main() -> int:
    if not GUI.is_file():
        print(f"ERROR: missing {GUI}", file=sys.stderr)
        return 1
    original = GUI.read_text(encoding="utf-8")
    text, c1 = patch_chain(original)
    text, c2 = patch_js(text)
    if c1 or c2:
        GUI.write_text(text, encoding="utf-8")
        print(f"patched: {GUI}")
    else:
        print(f"unchanged: {GUI}")
    errs = 0
    if MARKER not in text:
        print("ERROR: upload settle marker missing", file=sys.stderr)
        errs += 1
    if text.count('show_progress="hidden"') < 3:
        print("ERROR: expected >=3 hidden progress on then-chain", file=sys.stderr)
        errs += 1
    if JS_MARKER not in text:
        print("ERROR: upload settle js missing", file=sys.stderr)
        errs += 1
    try:
        compile(text, str(GUI), "exec")
    except SyntaxError as e:
        print(f"ERROR: syntax: {e}", file=sys.stderr)
        errs += 1
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
