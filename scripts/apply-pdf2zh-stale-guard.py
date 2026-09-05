#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-020：前端看门狗，消除「永久转圈且无任何提示」。

两类静默失败：
1. 服务重启后组件树换代，仍开着的旧页面 fn_index 与服务端错位，
   操作发出去但回执映射不到组件；
2. SSE 回执流中断，事件结果没送达。

两种情况下 Gradio 都不会解除加载态，页面只剩一个无限累加的计时器。
本补丁用 app_id 漂移检测 + 回执计数给出明确文案和刷新入口。

须在 apply-pdf2zh-left-dock.py 之后执行。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)

JS_MARKER = "_qy_stale_guard_js"
CSS_MARKER = "/* _qy_stale_guard_css */"

ANCHOR = "  window.__qyPageSyncInstalled = true;\n"

JS_BLOCK = """
  // _qy_stale_guard_js
  (function () {
    var APP_ID = (window.gradio_config && window.gradio_config.app_id) || null;
    var banner = null;
    var pending = 0;
    var lastDataOpen = 0;

    function showBanner(msg) {
      if (banner) return;
      banner = document.createElement('div');
      banner.className = 'qy-stale-banner';
      var text = document.createElement('span');
      text.textContent = msg;
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = '\\u5237\\u65b0\\u9875\\u9762';
      btn.onclick = function () { location.reload(); };
      banner.appendChild(text);
      banner.appendChild(btn);
      document.body.appendChild(banner);
    }

    // 服务重启会换 app_id，此时页面里的组件树与事件索引已过期
    function checkAppId() {
      if (!APP_ID) return;
      fetch('/config', { cache: 'no-store' })
        .then(function (r) { return r.json(); })
        .then(function (cfg) {
          if (cfg && cfg.app_id && cfg.app_id !== APP_ID) {
            showBanner('\\u670d\\u52a1\\u5df2\\u66f4\\u65b0\\uff0c\\u5f53\\u524d\\u9875\\u9762\\u7684\\u754c\\u9762\\u7248\\u672c\\u5df2\\u8fc7\\u671f\\uff0c\\u64cd\\u4f5c\\u4e0d\\u4f1a\\u751f\\u6548\\u3002');
          }
        })
        .catch(function () {});
    }
    checkAppId();
    setInterval(checkAppId, 30000);

    function watchStream(res) {
      var body;
      try { body = res.clone().body; } catch (e) { return; }
      if (!body) return;
      var reader = body.getReader();
      var dec = new TextDecoder();
      (function pump() {
        reader.read().then(function (chunk) {
          if (chunk.done) {
            if (pending > 0) {
              setTimeout(function () {
                // 客户端通常会立刻重开一条流；只有确实没重连才判定为丢失
                if (pending > 0 && Date.now() - lastDataOpen > 4000) {
                  showBanner('\\u4e0e\\u670d\\u52a1\\u5668\\u7684\\u8fde\\u63a5\\u4e2d\\u65ad\\uff0c\\u672c\\u6b21\\u64cd\\u4f5c\\u7684\\u7ed3\\u679c\\u6ca1\\u6709\\u9001\\u8fbe\\u3002');
                }
              }, 5000);
            }
            return;
          }
          var hits = dec.decode(chunk.value, { stream: true })
            .match(/"msg":[ ]*"process_completed"/g);
          if (hits) pending = Math.max(0, pending - hits.length);
          pump();
        }).catch(function () {});
      })();
    }

    var origFetch = window.fetch;
    window.fetch = function (input) {
      var url = String((input && input.url) || input || '');
      var p = origFetch.apply(this, arguments);
      if (url.indexOf('/queue/join') >= 0) {
        pending++;
      } else if (url.indexOf('/queue/data') >= 0) {
        lastDataOpen = Date.now();
        p.then(watchStream).catch(function () {});
      }
      return p;
    };
  })();
  // _qy_stale_guard_js_end
"""

CSS_BLOCK = """
    /* _qy_stale_guard_css */
    .qy-stale-banner {
        position: fixed;
        left: 50%;
        bottom: 24px;
        transform: translateX(-50%);
        z-index: 9999;
        display: flex;
        align-items: center;
        gap: 12px;
        max-width: min(92vw, 640px);
        padding: 10px 14px;
        border: 1px solid #fca5a5;
        border-radius: 10px;
        background: #fef2f2;
        color: #7f1d1d;
        font-size: 13px;
        line-height: 1.5;
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
    }
    .qy-stale-banner button {
        flex: none;
        padding: 4px 12px;
        border: 1px solid #dc2626;
        border-radius: 6px;
        background: #dc2626;
        color: #fff;
        font-size: 13px;
        cursor: pointer;
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
    span = _custom_css_span(text)
    if not span:
        print("WARNING: custom_css span missing", file=sys.stderr)
        return text, False
    c0, c1 = span
    css_body = text[c0:c1]
    if CSS_MARKER in css_body and text.count(CSS_MARKER) == 1:
        return text, False
    new_body = css_body.rstrip() + "\n" + CSS_BLOCK.rstrip() + "\n"
    return text[:c0] + new_body + text[c1:], True


JS_END_MARKER = JS_MARKER + "_end"

# 用显式结束标记界定，块内还有别的 `})();`，不能靠它收尾
JS_BLOCK_RE = re.compile(
    r"\n[ \t]*// " + JS_MARKER + r"\n.*?\n[ \t]*// " + JS_END_MARKER + r"\n",
    re.S,
)
# 迁移无结束标记的早期片段：外层 IIFE 收在两个空格缩进，块内的都更深
JS_LEGACY_RE = re.compile(
    r"\n[ \t]*// " + JS_MARKER + r"\n.*?\n  \}\)\(\);\n",
    re.S,
)


def apply_js(text: str) -> tuple[str, bool]:
    if JS_MARKER in text:
        # 自愈：既有片段与当前版本不一致时整块替换
        m = JS_BLOCK_RE.search(text) or JS_LEGACY_RE.search(text)
        if not m:
            print("WARNING: stale guard block not matchable", file=sys.stderr)
            return text, False
        if m.group(0).rstrip() == JS_BLOCK.rstrip():
            return text, False
        return text[: m.start()] + JS_BLOCK.rstrip() + "\n" + text[m.end() :], True
    if ANCHOR not in text:
        print("WARNING: page sync anchor missing; skip stale guard js", file=sys.stderr)
        return text, False
    return text.replace(ANCHOR, ANCHOR + JS_BLOCK, 1), True


def apply(text: str) -> tuple[str, bool]:
    changed = False
    for fn in (apply_js, apply_css):
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

    need(text.count("// " + JS_MARKER + "\n") == 1, "stale guard js missing or duplicated")
    need(text.count("// " + JS_END_MARKER) == 1, "stale guard end marker missing or duplicated")
    need(
        text.count("var origFetch = window.fetch;") == 1,
        "fetch wrapper duplicated (block boundary drifted)",
    )
    need(text.count(CSS_MARKER) == 1, "stale guard css missing or duplicated")
    span = _custom_css_span(text)
    need(span is not None, "custom_css missing")
    if span:
        need(CSS_MARKER in text[span[0] : span[1]], "banner css not inside custom_css")
    guard_i = text.find("// " + JS_MARKER)
    dock_i = text.find("// _qy_left_dock_js")
    need(
        dock_i < 0 or guard_i < dock_i,
        "stale guard js must precede dock js (dock patch rewrites its own tail block)",
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
