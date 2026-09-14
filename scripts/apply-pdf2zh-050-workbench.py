#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-050 工作台壳层 + PLAN-056/057 应用栏去重与高级区滚动。

须在 viewer / prescan / left-dock 之后执行。幂等。
禁止写入 Gradio js= / head=（会白屏）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)

CSS_MARKER = "/* _qy_050_workbench_css */"
JS_MARKER = "_qy_050_workbench_js"
JS_END = JS_MARKER + "_end"
PY_MARKER = "# _qy_050_prescan_card"
HEAD_MARKER = "<!-- _qy_050_head -->"

CSS_BLOCK = r"""
    /* _qy_050_workbench_css */
    :root {
      --qy-color-bg: #f4f6f8;
      --qy-color-surface: #ffffff;
      --qy-color-text: #1e293b;
      --qy-color-muted: #5b6b7a;
      --qy-color-border: #d5dde5;
      --qy-color-accent: #1f4e79;
      --qy-color-accent-fg: #ffffff;
      --qy-color-danger: #b42318;
      --qy-color-warn: #b45309;
      --qy-color-ok: #17635a;
      --qy-space-2: 8px;
      --qy-space-3: 12px;
      --qy-space-4: 16px;
      --qy-radius: 8px;
      --qy-focus: 2px solid #1f4e79;
      --qy-appbar-h: 48px;
      --qy-touch: 44px;
    }
    .qy-050-appbar {
      position: sticky; top: 0; z-index: 80;
      display: grid !important;
      grid-template-columns: max-content max-content minmax(112px, 136px) max-content minmax(96px, 120px) max-content max-content;
      align-items: center;
      column-gap: var(--qy-space-2);
      min-height: var(--qy-appbar-h);
      height: var(--qy-appbar-h) !important;
      max-height: var(--qy-appbar-h) !important;
      padding: 6px var(--qy-space-4);
      box-sizing: border-box;
      overflow: hidden !important;
      white-space: nowrap;
      background: var(--qy-color-accent);
      border-bottom: 1px solid var(--qy-color-border);
      color: var(--qy-color-accent-fg);
      font-family: system-ui, sans-serif;
    }
    .qy-050-appbar > *,
    .qy-050-appbar > .form, .qy-050-appbar .wrap,
    .qy-050-appbar .contain, .qy-050-appbar label {
      flex: 0 0 auto !important;
      width: auto !important;
      min-width: 0 !important;
      min-height: 0 !important;
      height: auto !important;
      max-height: none !important;
      margin: 0 !important;
    }
    .qy-050-appbar .block-label,
    .qy-050-appbar legend {
      width: auto !important;
      min-height: 0 !important;
      margin: 0 !important;
      padding: 0 !important;
    }
    .qy-050-appbar .qy-050-control-label {
      color: #fff !important;
      font-size: 12px !important;
      font-weight: 600 !important;
      line-height: 32px !important;
      background: transparent !important;
    }
    .qy-050-appbar .qy-050-control,
    .qy-050-appbar .qy-050-control .wrap,
    .qy-050-appbar .qy-050-control .form,
    .qy-050-appbar .qy-050-control > div {
      min-width: 0 !important;
      width: 100% !important;
      height: 34px !important;
      max-height: 34px !important;
      overflow: hidden !important;
      box-sizing: border-box !important;
    }
    .qy-050-appbar .qy-050-control input,
    .qy-050-appbar .qy-050-control button,
    .qy-050-appbar .qy-050-control [role="combobox"] {
      min-height: 32px !important;
      height: 32px !important;
      max-height: 32px !important;
      line-height: 30px !important;
      overflow: hidden !important;
      text-overflow: ellipsis !important;
      white-space: nowrap !important;
      box-sizing: border-box !important;
    }
    .qy-050-appbar .qy-050-control .label-wrap,
    .qy-050-appbar .qy-050-control .block-label,
    .qy-050-appbar .qy-050-control label {
      display: none !important;
    }
    .qy-050-appbar button {
      flex: 0 0 auto !important;
      min-height: 36px;
      min-width: 72px;
      max-width: 120px;
      border: 1px solid rgba(255,255,255,.35);
      border-radius: var(--qy-radius);
      background: transparent;
      color: var(--qy-color-accent-fg);
      font-size: 13px;
      padding: 4px 10px;
    }
    .qy-050-appbar .qy-050-status {
      flex: 0 0 auto;
      font-weight: 600;
      white-space: nowrap;
      color: #fff !important;
      background: transparent !important;
      line-height: 32px !important;
    }
    .qy-050-appbar .qy-050-status,
    .qy-050-appbar .qy-050-status *,
    .qy-050-appbar .qy-050-status p { color: #fff !important; background: transparent !important; }
    .qy-050-appbar *:focus-visible,
    .qy-col-left button:focus-visible,
    .qy-col-left input:focus-visible,
    .qy-col-left select:focus-visible,
    .qy-050-inspector button:focus-visible,
    .qy-050-inspector a:focus-visible,
    .qy-050-help button:focus-visible {
      outline: var(--qy-focus) !important;
      outline-offset: 2px !important;
    }
    .qy-050-status[data-state="failed"],
    .qy-050-status[data-state="blocked"] { color: var(--qy-color-danger); }
    .qy-050-status[data-state="degraded"] { color: var(--qy-color-warn); }
    .qy-050-status[data-state="succeeded"],
    .qy-050-status[data-state="review_ready"] { color: var(--qy-color-ok); }
    /* PLAN-057: help/inspector are toggle panels (no Accordion chrome) */
    .qy-050-inspector, .qy-050-help {
      margin: var(--qy-space-2) var(--qy-space-4);
      padding: var(--qy-space-3) var(--qy-space-4);
      background: var(--qy-color-surface);
      border: 1px solid var(--qy-color-border);
      border-radius: var(--qy-radius);
      color: var(--qy-color-text);
      font-family: system-ui, sans-serif;
    }
    /* PLAN-057: hide duplicate language row (qy_dir is SSOT for users) */
    .qy-col-left .lang-row {
      display: none !important;
    }
    /* 上传后预扫描摘要会把原本位于选项末尾的主操作推到首屏外；
       将主操作提升为左栏首个、始终可见的操作条。 */
    .qy-col-left > .action-row {
      order: -1 !important;
      display: flex !important;
      flex-flow: row nowrap !important;
      align-items: center !important;
      visibility: visible !important;
      opacity: 1 !important;
      position: sticky !important;
      top: 0 !important;
      bottom: auto !important;
      z-index: 35 !important;
      background: var(--qy-color-surface) !important;
      padding-top: 8px !important;
      padding-bottom: 8px !important;
      margin-top: 0 !important;
      box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06) !important;
    }
    .qy-col-left > .action-row > *,
    .qy-col-left > .action-row .action-btn,
    .qy-col-left > .action-row .action-btn button {
      display: flex !important;
      visibility: visible !important;
      opacity: 1 !important;
      min-height: var(--qy-touch) !important;
    }
    .qy-col-left > .action-row > * {
      flex: 1 1 0 !important;
      min-width: 0 !important;
    }
    /* PLAN-057: adv scroll override also applied after left-dock via apply_adv_scroll */
    .qy-col-left > .qy-adv-acc {
      overflow: visible !important;
    }
    .qy-col-left > .qy-adv-acc > :last-child {
      max-height: min(55vh, 560px) !important;
      overflow-y: auto !important;
      overflow-x: visible !important;
      overscroll-behavior: contain;
    }
    .qy-col-left .qy-adv-acc [role="listbox"],
    .qy-col-left .qy-adv-acc .options,
    .qy-col-left .qy-adv-acc ul[role="listbox"] {
      z-index: 40 !important;
    }
    .qy-050-card {
      border: 1px solid var(--qy-color-border);
      border-radius: var(--qy-radius);
      padding: var(--qy-space-3);
      margin-bottom: var(--qy-space-3);
    }
    .qy-050-skip-tech .qy-adv-acc { display: none !important; }
    body.qy-050-quick .qy-adv-acc { display: none !important; }
    @media (max-width: 1023px) {
      .qy-main-inner-row { flex-direction: column !important; }
      .qy-col-mid, .qy-col-right { width: 100% !important; min-width: 0 !important; }
      body.qy-050-src-only .qy-col-right { display: none !important; }
      body.qy-050-dst-only .qy-col-mid { display: none !important; }
    }
    @media (max-width: 767px) {
      .qy-col-left { width: 100% !important; }
      .qy-050-appbar {
        grid-template-columns: max-content minmax(104px, 1fr) max-content minmax(92px, 1fr) !important;
        grid-auto-rows: 34px !important;
        height: auto !important;
        max-height: none !important;
        white-space: normal;
      }
    }
    .sr-only {
      position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
      overflow: hidden; clip: rect(0,0,0,0); border: 0;
    }
"""

JS_BLOCK = r"""
  // _qy_050_workbench_js
  (function () {
    if (window.__qy050Installed) return;
    window.__qy050Installed = true;
    var MODE_KEY = 'qy050.mode';
    var CANVAS_KEY = 'qy050.canvas';

    function el(tag, attrs, kids) {
      var n = document.createElement(tag);
      attrs = attrs || {};
      Object.keys(attrs).forEach(function (k) {
        if (k === 'text') n.textContent = attrs[k];
        else n.setAttribute(k, attrs[k]);
      });
      (kids || []).forEach(function (c) { n.appendChild(c); });
      return n;
    }

    function currentMode() {
      return localStorage.getItem(MODE_KEY) === 'pro' ? 'pro' : 'quick';
    }
    function setMode(m) {
      localStorage.setItem(MODE_KEY, m);
      document.body.classList.toggle('qy-050-quick', m === 'quick');
      var btn = document.getElementById('qy050-mode');
      if (btn) {
        btn.setAttribute('aria-pressed', m === 'pro' ? 'true' : 'false');
        btn.textContent = m === 'pro' ? '专业模式' : '快速模式';
      }
    }
    function setCanvas(which) {
      localStorage.setItem(CANVAS_KEY, which);
      document.body.classList.toggle('qy-050-src-only', which === 'src');
      document.body.classList.toggle('qy-050-dst-only', which === 'dst');
    }

    function ensureChrome() {
      if (document.getElementById('qy050-appbar')) return;
      var bar = el('div', {id: 'qy050-appbar', 'class': 'qy-050-appbar', role: 'banner'});
      bar.appendChild(el('strong', {id: 'qy050-doc', text: '未选择文档'}));
      var dir = el('span', {id: 'qy050-dir', 'class': 'qy-050-dir', 'aria-live': 'polite', text: '英 → 中'});
      var st = el('span', {id: 'qy050-status', 'class': 'qy-050-status', 'data-state': 'queued', text: '就绪'});
      var mode = el('button', {id: 'qy050-mode', type: 'button', text: '快速模式'});
      mode.addEventListener('click', function () {
        setMode(currentMode() === 'quick' ? 'pro' : 'quick');
      });
      var help = el('button', {id: 'qy050-help', type: 'button', text: '帮助'});
      help.addEventListener('click', function () {
        alert('上传文件 → 确认预扫描摘要 → 翻译。专业模式打开对象/术语/QA 检查器。原文只读。');
      });
      var insp = el('button', {id: 'qy050-insp-btn', type: 'button', text: '检查器'});
      insp.addEventListener('click', function () { toggleInspector(); });
      var swap = el('button', {id: 'qy050-swap', type: 'button', text: '原文/译文'});
      swap.addEventListener('click', function () {
        var now = localStorage.getItem(CANVAS_KEY) === 'src' ? 'dst' : 'src';
        if (window.innerWidth >= 1024) now = 'both';
        setCanvas(now === 'both' ? 'both' : now);
      });
      bar.appendChild(dir);
      bar.appendChild(st);
      bar.appendChild(mode);
      bar.appendChild(swap);
      bar.appendChild(insp);
      bar.appendChild(help);
      document.body.insertBefore(bar, document.body.firstChild);

      var drawer = el('aside', {
        id: 'qy050-inspector',
        'class': 'qy-050-inspector',
        role: 'complementary',
        'aria-label': '对象检查器',
        'data-open': 'false'
      });
      drawer.appendChild(el('h2', {text: '检查器'}));
      drawer.appendChild(el('div', {id: 'qy050-sum', 'class': 'qy-050-card', text: '预扫描后显示 Figure / Table / 页数。缺失计数显示为横杠，不会填 0。'}));
      var obj = el('div', {id: 'qy050-obj', 'class': 'qy-050-card'});
      obj.appendChild(el('strong', {text: '对象'}));
      obj.appendChild(el('p', {text: '从摘要或 QA 跳转 page_id / object_id。原文只读。'}));
      obj.appendChild(el('label', {'for': 'qy050-page', text: '页'}));
      obj.appendChild(el('input', {id: 'qy050-page', type: 'number', min: '1', value: '1'}));
      obj.appendChild(el('button', {id: 'qy050-jump', type: 'button', text: '定位'}));
      drawer.appendChild(obj);
      var tm = el('div', {id: 'qy050-tm', 'class': 'qy-050-card'});
      tm.appendChild(el('strong', {text: '术语 / TM'}));
      tm.appendChild(el('p', {id: 'qy050-tm-body', text: '精确命中才 reuse。语义建议仅供审校。'}));
      drawer.appendChild(tm);
      var qa = el('div', {id: 'qy050-qa', 'class': 'qy-050-card'});
      qa.appendChild(el('strong', {text: 'QA'}));
      qa.appendChild(el('p', {id: 'qy050-qa-body', text: '无阻断问题时可正式导出；否则仅审阅稿。'}));
      drawer.appendChild(qa);
      drawer.appendChild(el('button', {id: 'qy050-insp-close', type: 'button', text: '关闭'}));
      document.body.appendChild(drawer);
      document.getElementById('qy050-insp-close').addEventListener('click', function () {
        toggleInspector(false);
      });
      document.getElementById('qy050-jump').addEventListener('click', function () {
        var p = parseInt(document.getElementById('qy050-page').value, 10) || 1;
        window.dispatchEvent(new CustomEvent('qy050:goto-page', {detail: {page: p}}));
        var hint = document.querySelector('.qy-preview-src, .qy-preview-dst');
        if (hint) hint.scrollIntoView({block: 'nearest'});
      });
    }

    function toggleInspector(force) {
      var d = document.getElementById('qy050-inspector');
      if (!d) return;
      var open = force === undefined ? d.getAttribute('data-open') !== 'true' : !!force;
      d.setAttribute('data-open', open ? 'true' : 'false');
      var btn = document.getElementById('qy050-insp-btn');
      if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (!open && btn) btn.focus();
    }

    function syncLabels() {
      var doc = document.querySelector('label, .qy-col-left');
      var sel = document.querySelector('.qy-col-left input[type=file], [aria-label*="upload" i]');
      var nameEl = document.getElementById('qy050-doc');
      var files = document.querySelector('.uploaded-files-list, .file-name, [data-testid="file"]');
      if (nameEl && files && files.textContent) {
        var t = files.textContent.trim().split('\n')[0];
        if (t) nameEl.textContent = t.slice(0, 80);
      }
      var from = document.querySelector('label');
      void from; void sel; void doc;
      var statusEl = document.getElementById('qy050-status');
      var prog = document.querySelector('.qy-progress-slot, .qy-prescan-bar');
      if (statusEl && prog) {
        var raw = (prog.textContent || '').toLowerCase();
        var state = 'queued';
        if (raw.indexOf('失败') >= 0 || raw.indexOf('error') >= 0) state = 'failed';
        else if (raw.indexOf('取消') >= 0) state = 'cancelled';
        else if (raw.indexOf('预扫') >= 0 || raw.indexOf('scan') >= 0) state = 'scanning';
        else if (raw.indexOf('翻译') >= 0) state = 'translating';
        else if (raw.indexOf('完成') >= 0) state = 'succeeded';
        statusEl.setAttribute('data-state', state);
        statusEl.textContent = ({
          queued: '就绪', scanning: '预扫描', translating: '翻译中',
          succeeded: '完成', failed: '失败', cancelled: '已取消'
        })[state] || state;
      }
      var prescan = document.querySelector('.qy-prescan-bar');
      var sum = document.getElementById('qy050-sum');
      if (prescan && sum && prescan.textContent) {
        sum.textContent = prescan.textContent.trim().slice(0, 400);
      }
    }

    function bindKeys() {
      if (window.__qy050Keys) return;
      window.__qy050Keys = true;
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') toggleInspector(false);
        if (e.altKey && e.key === '1') { e.preventDefault(); setCanvas('src'); }
        if (e.altKey && e.key === '2') { e.preventDefault(); setCanvas('dst'); }
        if (e.altKey && e.key === 'i') { e.preventDefault(); toggleInspector(); }
      });
    }

    function boot() {
      ensureChrome();
      setMode(currentMode());
      setCanvas(window.innerWidth >= 1024 ? 'both' : 'src');
      bindKeys();
      syncLabels();
    }
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', boot);
    } else {
      boot();
    }
    setInterval(syncLabels, 2000);
  })();
  // _qy_050_workbench_js_end
"""

PY_HOOK = """
                # _qy_050_prescan_card
                try:
                    from qyunslation.ui.manifest_view import render_prescan_card
                    text = render_prescan_card(manifest_json, fallback=text)
                except Exception:
                    pass
"""


HEAD_BLOCK = (
    '    head="""'
    + HEAD_MARKER
    + "\n<script>\n"
    + JS_BLOCK
    + "\n</script>\n"
    + '""",\n'
)


def apply_head(text: str) -> tuple[str, bool]:
    if HEAD_MARKER in text:
        return text, False
    needle = "    css=custom_css,\n"
    if needle not in text:
        return text, False
    return text.replace(needle, needle + HEAD_BLOCK, 1), True


def apply_css(text: str) -> tuple[str, bool]:
    replacement = CSS_BLOCK.lstrip("\n")
    if not replacement.endswith("\n"):
        replacement += "\n"
    if CSS_MARKER in text:
        pat = re.compile(
            r"    /\* _qy_050_workbench_css \*/.*?(?=    /\* _qy_(?!050_workbench_css))",
            re.S,
        )
        m = pat.search(text)
        if not m:
            return text, False
        if m.group(0) == replacement:
            return text, False
        return text[: m.start()] + replacement + text[m.end() :], True
    anchor = "    /* _qy_viewer_css */"
    if anchor in text:
        return text.replace(anchor, replacement + "\n" + anchor, 1), True
    marker = "    /* _qy_stale_guard_css */"
    if marker in text:
        return text.replace(marker, replacement + "\n" + marker, 1), True
    return text, False


def apply_js(text: str) -> tuple[str, bool]:
    """禁止再写入 Gradio js=：会拖垮整段官方函数导致白屏。"""
    return text, False


HTML_BEGIN = "# _qy_057_appbar_begin"
HTML_END = "# _qy_057_appbar_end"
HTML_BLOCK = f"""        {HTML_BEGIN}
        with gr.Row(elem_classes=["qy-050-appbar"]):
            gr.Markdown(
                "**就绪**",
                elem_classes=["qy-050-status"],
            )
            gr.Markdown("方向", elem_classes=["qy-050-control-label"])
            qy_dir = gr.Dropdown(
                choices=["英→中", "中→英"],
                value="英→中",
                show_label=False,
                container=False,
                scale=0,
                min_width=112,
                elem_classes=["qy-050-control", "qy-050-dir"],
            )
            gr.Markdown("模式", elem_classes=["qy-050-control-label"])
            qy_mode = gr.Dropdown(
                choices=["快速", "专业"],
                value="快速",
                show_label=False,
                container=False,
                scale=0,
                min_width=96,
                elem_classes=["qy-050-control", "qy-050-mode"],
            )
            qy_help_btn = gr.Button("帮助", scale=0, min_width=72, size="sm")
            qy_insp_btn = gr.Button("检查器", scale=0, min_width=72, size="sm")
        qy_help = gr.Column(
            visible=False,
            elem_classes=["qy-050-help"],
        )
        with qy_help:
            gr.Markdown(
                "1. 上传 PDF / Word / 图片 / PPT\\n"
                "2. 看左侧预扫描摘要（Figure/Table 来自结构清单；截断显示横杠，不用 0 冒充）\\n"
                "3. 点左侧「翻译」；取消只走手动取消\\n"
                "4. 专业模式才显示高级选项（页范围、术语表、水印）\\n"
                "原文只读。精确 TM 才 reuse，语义建议不自动套用。"
            )
        qy_inspector = gr.Column(
            visible=False,
            elem_classes=["qy-050-inspector"],
        )
        with qy_inspector:
            gr.Markdown(
                "- 预扫描与 manifest JSON 在左侧上传区\\n"
                "- QA：阻断问题禁止正式导出，审阅稿仍可下载\\n"
                "- 术语/TM：只把精确命中当 reuse\\n"
                "对象级单元格/OCR 编辑仍走既有预览与 BabelDOC，不另开引擎。"
            )
        qy_help_on = gr.State(False)
        qy_insp_on = gr.State(False)

        def _qy050_flip_help(on):
            on = not on
            return on, gr.update(visible=on)

        def _qy050_flip_insp(on):
            on = not on
            return on, gr.update(visible=on)

        qy_help_btn.click(_qy050_flip_help, [qy_help_on], [qy_help_on, qy_help])
        qy_insp_btn.click(_qy050_flip_insp, [qy_insp_on], [qy_insp_on, qy_inspector])
        {HTML_END}
"""

STATIC_BAR = """        gr.HTML(
            '<div class="qy-050-appbar" id="qy050-appbar" role="banner">'
            '<strong id="qy050-doc">Qyunslation 工作台</strong>'
            '<span class="qy-050-dir" id="qy050-dir">英 - 中</span>'
            '<span class="qy-050-status" id="qy050-status" data-state="queued">就绪</span>'
            '<span>快速模式 · 上传后预扫描 · 检查器见右栏专业流程</span>'
            "</div>"
        )
"""

_OLD_APPBAR_RE = re.compile(
    r'        with gr\.Row\(elem_classes=\["qy-050-appbar"\]\):.*?'
    r"qy_insp_btn\.click\(_qy050_flip_insp, \[qy_insp_on\], \[qy_insp_on, qy_inspector\]\)\n",
    re.S,
)
_MARKED_APPBAR_RE = re.compile(
    r"        # _qy_05[67]_appbar_begin\n.*?        # _qy_05[67]_appbar_end\n",
    re.S,
)


def apply_html(text: str) -> tuple[str, bool]:
    if HTML_BEGIN in text and "qy_dir = gr.Dropdown" in text and "qy_help = gr.Column(" in text:
        m = _MARKED_APPBAR_RE.search(text)
        if m and m.group(0) != HTML_BLOCK:
            return _MARKED_APPBAR_RE.sub(lambda _: HTML_BLOCK, text, count=1), True
        return text, False
    if _MARKED_APPBAR_RE.search(text):
        return _MARKED_APPBAR_RE.sub(lambda _: HTML_BLOCK, text, count=1), True
    if _OLD_APPBAR_RE.search(text):
        return _OLD_APPBAR_RE.sub(lambda _: HTML_BLOCK, text, count=1), True
    if STATIC_BAR in text:
        return text.replace(STATIC_BAR, HTML_BLOCK, 1), True
    brand_end = "        )\n\n        translation_engine_arg_inputs = []"
    if brand_end not in text:
        return text, False
    return text.replace(
        brand_end, "        )\n" + HTML_BLOCK + "\n        translation_engine_arg_inputs = []", 1
    ), True


ADV_OLD = '''                            with gr.Accordion(
                                "高级选项",
                                open=False,
                                elem_classes=["qy-adv-acc"],
                            ):'''
ADV_NEW = '''                            qy_adv_acc = gr.Accordion(
                                "高级选项",
                                open=False,
                                visible=False,
                                elem_classes=["qy-adv-acc"],
                            )
                            with qy_adv_acc:'''

LANG_ROW_OLD = 'with gr.Row(elem_classes=["lang-row"]):'
LANG_ROW_NEW = 'with gr.Row(elem_classes=["lang-row"], visible=False):'

EVT_BEGIN = "# _qy_057_events_begin"
EVT_END = "# _qy_057_events_end"
EVT_BLOCK = f"""        {EVT_BEGIN}
        def _qy050_mode(m):
            return gr.update(visible=(m == "专业"))

        def _qy056_dir_to_lang(d):
            if d == "中→英":
                return "Simplified Chinese", "English"
            return "English", "Simplified Chinese"

        def _qy056_lang_to_dir(lf, lt):
            if lf == "English" and lt == "Simplified Chinese":
                return gr.update(value="英→中")
            if lf == "Simplified Chinese" and lt == "English":
                return gr.update(value="中→英")
            return gr.update()

        qy_mode.change(_qy050_mode, [qy_mode], [qy_adv_acc])
        qy_dir.change(_qy056_dir_to_lang, [qy_dir], [lang_from, lang_to])
        lang_from.change(_qy056_lang_to_dir, [lang_from, lang_to], [qy_dir])
        lang_to.change(_qy056_lang_to_dir, [lang_from, lang_to], [qy_dir])
        {EVT_END}
"""

_OLD_EVT = """        def _qy050_mode(m):
            return gr.update(visible=(m == "专业"))

        qy_mode.change(_qy050_mode, [qy_mode], [qy_adv_acc])
"""
_MARKED_EVT_RE = re.compile(
    r"        # _qy_05[67]_events_begin\n.*?        # _qy_05[67]_events_end\n",
    re.S,
)


def apply_adv(text: str) -> tuple[str, bool]:
    changed = False
    if "qy_adv_acc = gr.Accordion(" not in text and ADV_OLD in text:
        text = text.replace(ADV_OLD, ADV_NEW, 1)
        changed = True
    if LANG_ROW_OLD in text and LANG_ROW_NEW not in text:
        text = text.replace(LANG_ROW_OLD, LANG_ROW_NEW, 1)
        changed = True
    if EVT_BEGIN in text and "qy_dir.change(" in text:
        m = _MARKED_EVT_RE.search(text)
        if m and m.group(0) != EVT_BLOCK:
            text = _MARKED_EVT_RE.sub(lambda _: EVT_BLOCK, text, count=1)
            changed = True
        return text, changed
    if _MARKED_EVT_RE.search(text):
        text = _MARKED_EVT_RE.sub(lambda _: EVT_BLOCK, text, count=1)
        changed = True
        return text, changed
    if _OLD_EVT in text:
        text = text.replace(_OLD_EVT, EVT_BLOCK, 1)
        changed = True
        return text, changed
    if "qy_mode.change(" not in text and "qy_adv_acc = gr.Accordion(" in text:
        hook = "        _qy_translate_evt = translate_btn.click("
        if hook not in text:
            return text, changed
        text = text.replace(hook, EVT_BLOCK + "\n" + hook, 1)
        changed = True
    return text, changed


def apply_adv_scroll(text: str) -> tuple[str, bool]:
    """覆盖 019 left-dock 的 38vh/340px（同特异性且其后写入会盖住 workbench CSS）。"""
    old = "min(38vh, 340px)"
    new = "min(55vh, 560px)"
    if old not in text:
        return text, False
    return text.replace(old, new), True


ACTION_GUARD_MARKER = "# _qy_060_upload_action_guard"
ACTION_GUARD_BLOCK = f'''        {ACTION_GUARD_MARKER}
        def _qy060_show_translate_action():
            return gr.update(visible=True, interactive=True)

        # Upload/change handlers must never leave the primary action hidden.
        file_input.upload(
            _qy060_show_translate_action,
            inputs=[],
            outputs=[translate_btn],
            queue=False,
        )
        file_input.change(
            _qy060_show_translate_action,
            inputs=[],
            outputs=[translate_btn],
            queue=False,
        )
'''


def apply_action_guard(text: str) -> tuple[str, bool]:
    """Keep the primary action visible after upload and file-list changes."""
    if ACTION_GUARD_MARKER in text:
        return text, False
    anchors = (
        "        # _qy_dual_clear\n",
        "        # Handle file clear/delete event\n",
    )
    for anchor in anchors:
        if anchor in text:
            return text.replace(anchor, ACTION_GUARD_BLOCK + "\n" + anchor, 1), True
    return text, False


def apply_py(text: str) -> tuple[str, bool]:
    if PY_MARKER in text:
        return text, False
    needle = "                import tempfile as _tmp\n"
    if needle not in text or PY_MARKER in text:
        return text, False
    return text.replace(needle, needle + PY_HOOK, 1), True


def strip_stale(text: str) -> tuple[str, bool]:
    """去掉 head= 副本和旧位置的 050 JS，再挂到 js= 函数开头。"""
    if JS_MARKER not in text and HEAD_MARKER not in text:
        return text, False

    n = 0
    text2, n1 = re.subn(
        r"\n    head=\"\"\"" + re.escape(HEAD_MARKER) + r".*?\"\"\",\n",
        "\n",
        text,
        count=1,
        flags=re.S,
    )
    n += n1
    text2, n2 = re.subn(
        r"\n  // " + re.escape(JS_MARKER) + r"\n.*?\n  // " + re.escape(JS_END) + r"\n",
        "\n",
        text2,
        count=2,
        flags=re.S,
    )
    n += n2
    return text2, n > 0


def apply(text: str) -> tuple[str, bool]:
    changed = False
    for fn in (
        strip_stale,
        apply_css,
        apply_js,
        apply_html,
        apply_adv,
        apply_adv_scroll,
        apply_action_guard,
        apply_py,
    ):
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

    need(text.count(CSS_MARKER) == 1, "050 css missing/dup")
    _offscreen = "translate" + "X(100%)"
    need(_offscreen not in text, "drawer offscreen transform must be gone")
    need(text.count("// " + JS_MARKER + "\n") == 0, "050 js must not sit in Gradio js=")
    need("qy_mode = gr.Dropdown" in text, "mode dropdown")
    need("qy_dir = gr.Dropdown" in text, "dir dropdown")
    need("qy_help = gr.Column(" in text, "help panel column")
    need("qy_inspector = gr.Column(" in text, "inspector panel column")
    _acc = "qy_help = gr." + "Accordion("
    _acc_i = "qy_inspector = gr." + "Accordion("
    need(_acc not in text, "help must not be Accordion")
    need(_acc_i not in text, "inspector must not be Accordion")
    need("qy_help_btn.click" in text, "help click")
    need("qy_insp_btn.click" in text, "inspector click")
    need("qy_adv_acc = gr.Accordion(" in text, "adv accordion named")
    need("qy_mode.change(" in text, "mode wires adv")
    need("qy_dir.change(" in text, "dir wires lang")
    need(ACTION_GUARD_MARKER in text, "upload action guard")
    need("_qy060_show_translate_action" in text, "translate action visibility callback")
    need("outputs=[translate_btn]" in text, "translate action visibility output")
    need('elem_classes=["lang-row"], visible=False' in text, "lang-row hidden")
    need("min(55vh, 560px)" in text, "adv scroll override")
    need("min(38vh, 340px)" not in text, "old left-dock lock height must be overridden")
    need("qy-050-appbar" in text, "appbar class")
    need("focus-visible" in text, "focus-visible")
    need("grid-template-columns" in text, "compact appbar grid")
    need("qy-050-control-label" in text, "control labels")
    need("color: #fff !important" in text, "status contrast")
    need("show_label=False" in text, "compact controls hide duplicate labels")
    need(PY_MARKER in text, "prescan card hook")
    need(HEAD_MARKER not in text, "stale head= still present")
    need("__qyPageSyncInstalled" in text, "page-sync kept")
    _bad_copy = "方向在" + "左侧"
    need(_bad_copy not in text, "confusing direction copy must be gone")
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
