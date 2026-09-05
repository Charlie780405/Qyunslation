#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-021：预览缩放/旋转/拖拽/全屏查看器。

参照 qyunsgen ScreeningDocumentViewer 的交互模型：
外层管 scale/translate，内层只管 90° 旋转；minScale=0.5 / maxScale=4。
纯原生 JS+CSS，同时适配 img、HTML 预览与 PDF canvas。

须在 apply-pdf2zh-css-has-fix.py 之后执行。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)

JS_MARKER = "_qy_viewer_js"
JS_END_MARKER = JS_MARKER + "_end"
CSS_MARKER = "/* _qy_viewer_css */"

# 挂在 stale-guard 结束标记之后；若无则挂在 page sync 锚点后
ANCHOR_PREF = "  // _qy_stale_guard_js_end\n"
ANCHOR_FALLBACK = "  window.__qyPageSyncInstalled = true;\n"

JS_BLOCK = r"""
  // _qy_viewer_js
  (function () {
    if (window.__qyViewerInstalled) return;
    window.__qyViewerInstalled = true;

    var MIN = 0.5, MAX = 4, STEP = 1.25;
    var SELECTORS = [
      '.qy-preview-src',
      '.qy-preview-dst',
      '.qy-preview-src-html',
      '.qy-preview-dst-html'
    ];

    function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

    function makeBtn(title, svg, onClick) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'qy-viewer-btn';
      b.title = title;
      b.setAttribute('aria-label', title);
      b.innerHTML = svg;
      b.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        onClick();
      });
      return b;
    }

    var ICONS = {
      zoomIn: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M11 8v6M8 11h6M21 21l-4.3-4.3"/></svg>',
      zoomOut: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M8 11h6M21 21l-4.3-4.3"/></svg>',
      rotL: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/></svg>',
      rotR: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v5h-5"/></svg>',
      reset: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3"/></svg>',
      full: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3"/></svg>',
      close: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>'
    };

    function applyState(state) {
      var s = 'translate(' + state.x + 'px,' + state.y + 'px) scale(' + state.scale + ')';
      state.stage.style.transform = s;
      state.inner.style.transform = 'rotate(' + state.rotation + 'deg)';
    }

    function resetState(state) {
      state.scale = 1;
      state.x = 0;
      state.y = 0;
      state.rotation = 0;
      applyState(state);
    }

    function zoomAt(state, factor, cx, cy) {
      var rect = state.viewport.getBoundingClientRect();
      var px = (cx != null ? cx : rect.left + rect.width / 2) - rect.left;
      var py = (cy != null ? cy : rect.top + rect.height / 2) - rect.top;
      var prev = state.scale;
      var next = clamp(prev * factor, MIN, MAX);
      if (next === prev) return;
      state.x = px - (px - state.x) * (next / prev);
      state.y = py - (py - state.y) * (next / prev);
      state.scale = next;
      applyState(state);
    }

    function bindGestures(state) {
      var vp = state.viewport;
      var dragging = false, lastX = 0, lastY = 0;
      var pinching = false, pinchDist = 0;

      vp.addEventListener('wheel', function (e) {
        e.preventDefault();
        zoomAt(state, e.deltaY < 0 ? STEP : 1 / STEP, e.clientX, e.clientY);
      }, { passive: false });

      vp.addEventListener('mousedown', function (e) {
        if (e.button !== 0) return;
        if (e.target.closest && e.target.closest('.qy-viewer-toolbar')) return;
        dragging = true;
        lastX = e.clientX;
        lastY = e.clientY;
        vp.classList.add('qy-viewer-dragging');
        e.preventDefault();
      });
      window.addEventListener('mousemove', function (e) {
        if (!dragging) return;
        state.x += e.clientX - lastX;
        state.y += e.clientY - lastY;
        lastX = e.clientX;
        lastY = e.clientY;
        applyState(state);
      });
      window.addEventListener('mouseup', function () {
        dragging = false;
        vp.classList.remove('qy-viewer-dragging');
      });

      vp.addEventListener('dblclick', function (e) {
        if (e.target.closest && e.target.closest('.qy-viewer-toolbar')) return;
        if (state.scale > 1.05) resetState(state);
        else zoomAt(state, 2, e.clientX, e.clientY);
      });

      vp.addEventListener('touchstart', function (e) {
        if (e.target.closest && e.target.closest('.qy-viewer-toolbar')) return;
        if (e.touches.length === 1) {
          dragging = true;
          lastX = e.touches[0].clientX;
          lastY = e.touches[0].clientY;
        } else if (e.touches.length === 2) {
          pinching = true;
          dragging = false;
          var dx = e.touches[0].clientX - e.touches[1].clientX;
          var dy = e.touches[0].clientY - e.touches[1].clientY;
          pinchDist = Math.hypot(dx, dy) || 1;
        }
      }, { passive: true });
      vp.addEventListener('touchmove', function (e) {
        if (pinching && e.touches.length === 2) {
          e.preventDefault();
          var dx = e.touches[0].clientX - e.touches[1].clientX;
          var dy = e.touches[0].clientY - e.touches[1].clientY;
          var dist = Math.hypot(dx, dy) || 1;
          var midX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
          var midY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
          zoomAt(state, dist / pinchDist, midX, midY);
          pinchDist = dist;
        } else if (dragging && e.touches.length === 1) {
          e.preventDefault();
          state.x += e.touches[0].clientX - lastX;
          state.y += e.touches[0].clientY - lastY;
          lastX = e.touches[0].clientX;
          lastY = e.touches[0].clientY;
          applyState(state);
        }
      }, { passive: false });
      vp.addEventListener('touchend', function () {
        dragging = false;
        pinching = false;
      });
    }

    function buildToolbar(state, opts) {
      var bar = document.createElement('div');
      bar.className = 'qy-viewer-toolbar';
      bar.appendChild(makeBtn('\u7f29\u5c0f', ICONS.zoomOut, function () { zoomAt(state, 1 / STEP); }));
      bar.appendChild(makeBtn('\u653e\u5927', ICONS.zoomIn, function () { zoomAt(state, STEP); }));
      bar.appendChild(makeBtn('\u9006\u65f6\u9488\u65cb\u8f6c', ICONS.rotL, function () {
        state.rotation = (state.rotation - 90 + 360) % 360;
        applyState(state);
      }));
      bar.appendChild(makeBtn('\u987a\u65f6\u9488\u65cb\u8f6c', ICONS.rotR, function () {
        state.rotation = (state.rotation + 90) % 360;
        applyState(state);
      }));
      bar.appendChild(makeBtn('\u91cd\u7f6e\u89c6\u56fe', ICONS.reset, function () { resetState(state); }));
      if (opts && opts.onFullscreen) {
        bar.appendChild(makeBtn('\u5168\u5c4f', ICONS.full, opts.onFullscreen));
      }
      if (opts && opts.onClose) {
        bar.appendChild(makeBtn('\u5173\u95ed', ICONS.close, opts.onClose));
      }
      return bar;
    }

    function openFullscreen(sourcePanel) {
      var existing = document.getElementById('qy-viewer-fs');
      if (existing) existing.remove();

      var overlay = document.createElement('div');
      overlay.id = 'qy-viewer-fs';
      overlay.className = 'qy-viewer-fs';

      var title = document.createElement('div');
      title.className = 'qy-viewer-fs-title';
      var label = sourcePanel.querySelector('img[alt], canvas');
      title.textContent = (label && (label.getAttribute('alt') || 'PDF')) || '\u9884\u89c8';

      var viewport = document.createElement('div');
      viewport.className = 'qy-viewer-viewport qy-viewer-fs-viewport';
      var stage = document.createElement('div');
      stage.className = 'qy-viewer-stage';
      var inner = document.createElement('div');
      inner.className = 'qy-viewer-inner';

      // clone visible content once (whole container); avoid matching nested img inside .prose
      var cloneRoot = sourcePanel.querySelector('.qy-viewer-inner') || sourcePanel;
      var clone = cloneRoot.cloneNode(true);
      var srcCanvases = cloneRoot.querySelectorAll('canvas');
      clone.querySelectorAll('canvas').forEach(function (c, i) {
        try {
          if (srcCanvases[i]) c.getContext('2d').drawImage(srcCanvases[i], 0, 0);
        } catch (err) {}
      });
      // strip nested toolbars from clone
      clone.querySelectorAll('.qy-viewer-toolbar').forEach(function (el) { el.remove(); });
      inner.appendChild(clone);

      stage.appendChild(inner);
      viewport.appendChild(stage);

      var state = {
        scale: 1, x: 0, y: 0, rotation: 0,
        viewport: viewport, stage: stage, inner: inner
      };
      var toolbar = buildToolbar(state, {
        onClose: function () { overlay.remove(); }
      });
      toolbar.classList.add('qy-viewer-fs-toolbar');

      var top = document.createElement('div');
      top.className = 'qy-viewer-fs-top';
      top.appendChild(title);
      top.appendChild(toolbar);

      overlay.appendChild(top);
      overlay.appendChild(viewport);
      document.body.appendChild(overlay);

      bindGestures(state);
      applyState(state);

      function onKey(e) {
        if (e.key === 'Escape') {
          overlay.remove();
          window.removeEventListener('keydown', onKey);
        }
      }
      window.addEventListener('keydown', onKey);
      overlay.addEventListener('click', function (e) {
        if (e.target === overlay) {
          overlay.remove();
          window.removeEventListener('keydown', onKey);
        }
      });
    }

    function enhancePanel(panel) {
      if (!panel || panel.dataset.qyViewer === '1') return;
      if (panel.classList.contains('hidden')) return;

      // need content
      var content = panel.querySelector('img, canvas, iframe, embed, .prose, .markdown, .html-container');
      if (!content && !panel.querySelector('.qy-html-preview-body')) return;

      panel.dataset.qyViewer = '1';
      panel.classList.add('qy-viewer-host');

      var viewport = document.createElement('div');
      viewport.className = 'qy-viewer-viewport';
      var stage = document.createElement('div');
      stage.className = 'qy-viewer-stage';
      var inner = document.createElement('div');
      inner.className = 'qy-viewer-inner';

      // move existing children into inner (except toolbars we might re-add)
      var movers = Array.prototype.slice.call(panel.childNodes);
      movers.forEach(function (n) {
        if (n.nodeType === 1 && n.classList && n.classList.contains('qy-viewer-toolbar')) return;
        inner.appendChild(n);
      });
      stage.appendChild(inner);
      viewport.appendChild(stage);
      panel.appendChild(viewport);

      var state = {
        scale: 1, x: 0, y: 0, rotation: 0,
        viewport: viewport, stage: stage, inner: inner
      };

      var toolbar = buildToolbar(state, {
        onFullscreen: function () { openFullscreen(panel); }
      });
      panel.appendChild(toolbar);
      bindGestures(state);
      applyState(state);

      // click image to open fullscreen (not during drag)
      var moved = false;
      viewport.addEventListener('mousedown', function () { moved = false; });
      viewport.addEventListener('mousemove', function () { moved = true; });
      viewport.addEventListener('click', function (e) {
        if (moved) return;
        if (e.target.closest && e.target.closest('.qy-viewer-toolbar')) return;
        if (e.target.tagName === 'IMG' || e.target.tagName === 'CANVAS') {
          openFullscreen(panel);
        }
      });
    }

    function scan() {
      SELECTORS.forEach(function (sel) {
        document.querySelectorAll(sel).forEach(enhancePanel);
      });
      // PDF without qy-preview-* class (legacy single preview)
      document.querySelectorAll('.qy-col-mid > .pdf-preview-fixed, .qy-col-right > .pdf-preview-fixed').forEach(enhancePanel);
      document.querySelectorAll('.qy-col-mid > .qy-html-preview-wrap, .qy-col-right > .qy-html-preview-wrap').forEach(enhancePanel);
    }

    scan();
    var obs = new MutationObserver(function () { scan(); });
    obs.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
  })();
  // _qy_viewer_js_end
"""

CSS_BLOCK = """
    /* _qy_viewer_css */
    .qy-viewer-host {
        position: relative !important;
        overflow: hidden !important;
    }
    .qy-viewer-viewport {
        width: 100%;
        height: 100%;
        overflow: hidden;
        cursor: grab;
        touch-action: none;
        background: transparent;
    }
    .qy-viewer-dragging { cursor: grabbing !important; }
    .qy-viewer-stage {
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        transform-origin: 0 0;
        will-change: transform;
    }
    .qy-viewer-inner {
        max-width: 100%;
        max-height: 100%;
        transform-origin: center center;
        will-change: transform;
    }
    .qy-viewer-inner img,
    .qy-viewer-inner canvas {
        max-width: 100%;
        max-height: 100%;
        object-fit: contain;
        display: block;
        user-select: none;
        -webkit-user-drag: none;
    }
    .qy-viewer-toolbar {
        position: absolute;
        top: 8px;
        right: 8px;
        z-index: 5;
        display: flex;
        gap: 2px;
        padding: 4px;
        border-radius: 8px;
        background: rgba(15, 23, 42, 0.55);
        opacity: 0;
        transition: opacity 0.15s ease;
        pointer-events: none;
    }
    .qy-viewer-host:hover .qy-viewer-toolbar,
    .qy-viewer-host:focus-within .qy-viewer-toolbar {
        opacity: 1;
        pointer-events: auto;
    }
    .qy-viewer-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 36px;
        min-height: 36px;
        padding: 0;
        border: 0;
        border-radius: 6px;
        background: transparent;
        color: #fff;
        cursor: pointer;
    }
    .qy-viewer-btn:hover { background: rgba(255, 255, 255, 0.15); }
    .qy-viewer-fs {
        position: fixed;
        inset: 0;
        z-index: 10000;
        display: flex;
        flex-direction: column;
        background: rgba(0, 0, 0, 0.82);
    }
    .qy-viewer-fs-top {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding: 10px 16px;
        color: #fff;
        flex: none;
    }
    .qy-viewer-fs-title {
        font-size: 14px;
        opacity: 0.9;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        max-width: 40vw;
    }
    .qy-viewer-fs-toolbar {
        position: static;
        opacity: 1 !important;
        pointer-events: auto !important;
        background: rgba(0, 0, 0, 0.4);
    }
    .qy-viewer-fs-viewport {
        flex: 1 1 auto;
        min-height: 0;
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


JS_BLOCK_RE = re.compile(
    r"\n[ \t]*// " + JS_MARKER + r"\n.*?\n[ \t]*// " + JS_END_MARKER + r"\n",
    re.S,
)


def apply_js(text: str) -> tuple[str, bool]:
    if JS_MARKER in text:
        m = JS_BLOCK_RE.search(text)
        if not m:
            print("WARNING: viewer js block not matchable", file=sys.stderr)
            return text, False
        if m.group(0).rstrip() == JS_BLOCK.rstrip():
            return text, False
        return text[: m.start()] + JS_BLOCK.rstrip() + "\n" + text[m.end() :], True
    anchor = ANCHOR_PREF if ANCHOR_PREF in text else ANCHOR_FALLBACK
    if anchor not in text:
        print("WARNING: viewer js anchor missing", file=sys.stderr)
        return text, False
    return text.replace(anchor, anchor + JS_BLOCK, 1), True


def apply_css(text: str) -> tuple[str, bool]:
    span = _custom_css_span(text)
    if not span:
        print("WARNING: custom_css span missing", file=sys.stderr)
        return text, False
    c0, c1 = span
    css_body = text[c0:c1]
    if CSS_MARKER in css_body:
        # replace existing block
        m = re.search(
            r"\n[ \t]*/\* _qy_viewer_css \*/.*?$(?=\n[ \t]*/\*|\n[ \t]*\"\"\"|\Z)",
            css_body,
            re.S | re.M,
        )
        if m and m.group(0).rstrip() == CSS_BLOCK.rstrip():
            return text, False
        if m:
            new_body = css_body[: m.start()] + "\n" + CSS_BLOCK.rstrip() + "\n" + css_body[m.end() :]
            return text[:c0] + new_body + text[c1:], True
    new_body = css_body.rstrip() + "\n" + CSS_BLOCK.rstrip() + "\n"
    return text[:c0] + new_body + text[c1:], True


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

    need(text.count("// " + JS_MARKER + "\n") == 1, "viewer js missing or duplicated")
    need(text.count("// " + JS_END_MARKER) == 1, "viewer js end missing or duplicated")
    need(text.count(CSS_MARKER) == 1, "viewer css missing or duplicated")
    need("qy-viewer-toolbar" in text, "toolbar class missing")
    need("qy-viewer-fs" in text, "fullscreen class missing")
    need("__qyViewerInstalled" in text, "idempotent guard missing")
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
