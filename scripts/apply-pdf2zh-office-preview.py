#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-014：Office/DOCX/MD/图片走 HTML 预览，避免 Gradio PDF() 白屏。uv 升级后重跑。"""
from __future__ import annotations

import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)
MARKER = "_qy_office_preview"


HELPER = r'''
# --- PLAN-014: non-PDF preview via HTML ---
_QY_PREVIEW_HTML_EXT = {".docx", ".doc", ".md", ".markdown", ".png", ".jpg", ".jpeg", ".webp", ".html", ".htm"}
_QY_MAMMOTH_PY = Path("/home/dev/qyunslation/.venv/bin/python")


def _qy_wrap_preview_html(body: str, title: str = "") -> str:
    safe_title = (title or "").replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<div class="qy-html-preview">'
        + (f"<h3 class='qy-html-preview-title'>{safe_title}</h3>" if safe_title else "")
        + f'<div class="qy-html-preview-body">{body}</div></div>'
    )


def _qy_docx_to_html(path: Path) -> str:
    """mammoth → HTML；pdf2zh 环境无包时回退到 qyunslation venv。"""
    data = path.read_bytes()
    try:
        import mammoth
        from io import BytesIO

        return mammoth.convert_to_html(BytesIO(data)).value or ""
    except Exception:
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp:
            out = Path(tmp.name)
        try:
            script = (
                "import sys; from io import BytesIO; import mammoth; "
                "html=mammoth.convert_to_html(BytesIO(sys.stdin.buffer.read())).value; "
                f"open({str(out)!r},'w',encoding='utf-8').write(html or '')"
            )
            subprocess.run(
                [str(_QY_MAMMOTH_PY), "-c", script],
                input=data,
                check=True,
                timeout=120,
            )
            return out.read_text(encoding="utf-8")
        finally:
            out.unlink(missing_ok=True)


def _qy_md_to_html(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        import html as _html
        import re

        # 极简：转义后把标题/段落换成标签，避免强依赖 markdown 包
        esc = _html.escape(text)
        lines = []
        for line in esc.splitlines():
            if line.startswith("### "):
                lines.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("## "):
                lines.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("# "):
                lines.append(f"<h1>{line[2:]}</h1>")
            elif not line.strip():
                lines.append("<br/>")
            else:
                lines.append(f"<p>{line}</p>")
        return "\n".join(lines)
    except Exception:
        return f"<pre>{text}</pre>"


def _qy_hide_pdf():
    return gr.update(value=None, visible=False)


def _qy_show_pdf(path: str):
    return gr.update(value=path, visible=True)


def _qy_preview_payload(path_str: str | None) -> tuple:
    """返回 (pdf_update, html_update)。非 PDF 必须隐藏 PDF()，否则空壳占 75vh。"""
    if not path_str:
        return _qy_hide_pdf(), gr.update(value="", visible=False)
    path = Path(str(path_str))
    if not path.is_file():
        return _qy_hide_pdf(), gr.update(
            value=_qy_wrap_preview_html(f"<p>文件不存在：{path.name}</p>"),
            visible=True,
        )
    suf = path.suffix.lower()
    if suf == ".pdf":
        return _qy_show_pdf(str(path)), gr.update(value="", visible=False)
    # 优先旁路 html（office-route 下载的 sidecar 预览）
    for cand in (
        path.with_suffix(".html"),
        path.with_name(path.stem + ".html"),
        path.with_name(path.name.replace(".docx", ".html").replace(".doc", ".html")),
    ):
        if cand.is_file() and cand.suffix.lower() in {".html", ".htm"}:
            body = cand.read_text(encoding="utf-8", errors="replace")
            return _qy_hide_pdf(), gr.update(value=_qy_wrap_preview_html(body, path.name), visible=True)
    try:
        if suf in {".html", ".htm"}:
            body = path.read_text(encoding="utf-8", errors="replace")
        elif suf in {".docx", ".doc"}:
            body = _qy_docx_to_html(path)
            if not body.strip():
                body = "<p>（未能从 Word 提取预览内容，请直接下载）</p>"
        elif suf in {".md", ".markdown"}:
            body = _qy_md_to_html(path)
        elif suf in {".png", ".jpg", ".jpeg", ".webp"}:
            # Gradio 文件路径对浏览器不一定可访问；用 data URL
            import base64

            mime = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
            }.get(suf, "application/octet-stream")
            b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            body = f'<img src="data:{mime};base64,{b64}" alt="{path.name}" style="max-width:100%;height:auto;"/>'
        else:
            body = f"<p>暂不支持预览此格式（{suf or '无后缀'}），请下载查看。</p>"
    except Exception as exc:
        body = f"<p>预览失败：{_html_escape(str(exc))}</p>"
    return _qy_hide_pdf(), gr.update(value=_qy_wrap_preview_html(body, path.name), visible=True)


def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

'''


def apply(text: str) -> str:
    if MARKER in text and "preview_html = gr.HTML" in text:
        # still allow partial upgrades below
        pass
    else:
        # inject helper before update_preview
        anchor = "def update_preview(selected_label, state):"
        if MARKER not in text:
            if anchor not in text:
                raise RuntimeError("找不到 update_preview")
            text = text.replace(anchor, HELPER + "\n" + anchor, 1)

    # --- replace update_preview function (regex，抗空白漂移) ---
    new_update = '''def update_preview(selected_label, state):
    """
    Update preview based on selected label from dropdown.
    Modified to support previewing raw uploaded files before translation.
    PLAN-014: non-PDF → HTML preview (_qy_office_preview).
    """
    empty_html = gr.update(value="", visible=False)
    hide_pdf = gr.update(value=None, visible=False)
    # 1. Basic validation
    if not selected_label or not state or "display_map" not in state:
        return (
            None,
            hide_pdf,
            None,
            None,
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            empty_html,
        )

    # 1.5. Validate selected_label is in display_map (choices)
    # This prevents Gradio errors when value is not in choices
    if selected_label not in state.get("display_map", {}):
        # Reset to first available choice or None
        choices = list(state.get("display_map", {}).keys())
        selected_label = choices[0] if choices else None
        if not selected_label:
            return (
                None,
                hide_pdf,
                None,
                None,
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                empty_html,
            )

    # 2. Get the file path for the PDF / HTML viewer
    # This works for both uploaded files and translated files
    preview_path = state["display_map"].get(selected_label)

    if not preview_path:
        return (
            None,
            hide_pdf,
            None,
            None,
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            empty_html,
        )

    # 3. Try to get translation results for download buttons
    # If just uploaded (not translated), res will be None
    parent_key = state["parent_map"].get(selected_label)
    res = None
    if parent_key and "results" in state:
        res = state["results"].get(parent_key)

    # 4. Prepare return values
    # If res exists, show download buttons. If not, hide them.
    mono_path = res["mono"] if res else None
    dual_path = res["dual"] if res else None
    glossary_path = res["glossary"] if res else None
    pdf_path, html_update = _qy_preview_payload(preview_path)

    return (
        mono_path,  # Download Mono Button Value
        pdf_path,  # PDF Preview Value (None for Office)
        dual_path,  # Download Dual Button Value
        glossary_path,  # Download Glossary Button Value
        gr.update(visible=bool(mono_path)),  # Mono Button Visibility
        gr.update(visible=bool(dual_path)),  # Dual Button Visibility
        gr.update(visible=bool(glossary_path)),  # Glossary Button Visibility
        html_update,  # PLAN-014 HTML preview
    )


'''
    if "_qy_preview_payload(preview_path)" not in text:
        import re

        pat = re.compile(
            r"^def update_preview\(selected_label, state\):.*?(?=^def on_file_upload\()",
            re.M | re.S,
        )
        if not pat.search(text):
            raise RuntimeError("找不到 update_preview…on_file_upload 区间")
        text = pat.sub(new_update, text, count=1)

    # --- insert preview_html component ---
    pdf_anchor = '''                            preview = PDF(
                                label=None,
                                show_label=False,
                                visible=True,
                                elem_classes=["pdf-preview-fixed"],
                            )'''
    pdf_new = '''                            preview = PDF(
                                label=None,
                                show_label=False,
                                visible=True,
                                elem_classes=["pdf-preview-fixed"],
                            )
                            # _qy_office_preview
                            preview_html = gr.HTML(
                                value="",
                                visible=False,
                                elem_classes=["qy-html-preview-wrap"],
                            )'''
    if "preview_html = gr.HTML" not in text:
        if pdf_anchor not in text:
            raise RuntimeError("找不到 PDF() 预览组件")
        text = text.replace(pdf_anchor, pdf_new, 1)

    # --- CSS ---
    css_marker = "    .qy-html-preview-wrap {"
    if css_marker not in text:
        css_insert = """
    .qy-html-preview-wrap {
        max-height: min(70vh, 820px);
        overflow: auto;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        background: #fff;
        padding: 12px 16px;
    }
    /* 非 PDF 预览时 PDF() 可能仍占 75vh 空壳 */
    .pdf-preview-fixed:not(:has(canvas)):not(:has(iframe)):not(:has(embed)) {
        display: none !important;
        height: 0 !important;
        max-height: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
        overflow: hidden !important;
        border: none !important;
    }
    .qy-html-preview-title {
        margin: 0 0 12px;
        font-size: 0.95rem;
        color: #64748b;
        font-weight: 500;
    }
    .qy-html-preview-body {
        line-height: 1.6;
        color: #0f172a;
        font-size: 0.95rem;
    }
    .qy-html-preview-body img {
        max-width: 100%;
        height: auto;
    }
"""
        needle = "    .pdf-preview-fixed [data-testid=\"block-label\"] {"
        if needle not in text:
            raise RuntimeError("找不到预览 CSS 锚点")
        text = text.replace(needle, css_insert + "\n" + needle, 1)

    # --- on_file_input_change unpack ---
    old_unpack = '''    mono_path, preview_path, dual_path, glossary_path, vis_mono, vis_dual, vis_glossary = (
        update_preview(selector_value, state)
        if selector_value
        else (
            None,
            None,
            None,
            None,
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
        )
    )

    return (
        selector_update,
        state,
        uploaded_view_update,
        preview_path,  # preview
        mono_path,
        dual_path,
        glossary_path,
        vis_mono,
        vis_dual,
        vis_glossary,
    )'''
    new_unpack = '''    mono_path, preview_path, dual_path, glossary_path, vis_mono, vis_dual, vis_glossary, preview_html_update = (
        update_preview(selector_value, state)
        if selector_value
        else (
            None,
            None,
            None,
            None,
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(value="", visible=False),
        )
    )

    return (
        selector_update,
        state,
        uploaded_view_update,
        preview_path,  # preview
        mono_path,
        dual_path,
        glossary_path,
        vis_mono,
        vis_dual,
        vis_glossary,
        preview_html_update,
    )'''
    if "preview_html_update" not in text or old_unpack in text:
        if old_unpack in text:
            text = text.replace(old_unpack, new_unpack, 1)

    # file_input.change outputs
    old_change_out = '''        file_input.change(
            on_file_input_change,
            inputs=[file_input, state, result_file_selector],
            outputs=[
                result_file_selector,
                state,
                uploaded_files_view,
                preview,
                output_file_mono,
                output_file_dual,
                output_file_glossary,
                output_file_mono,  # visibility
                output_file_dual,  # visibility
                output_file_glossary,  # visibility
            ],
        )'''
    new_change_out = '''        file_input.change(
            on_file_input_change,
            inputs=[file_input, state, result_file_selector],
            outputs=[
                result_file_selector,
                state,
                uploaded_files_view,
                preview,
                output_file_mono,
                output_file_dual,
                output_file_glossary,
                output_file_mono,  # visibility
                output_file_dual,  # visibility
                output_file_glossary,  # visibility
                preview_html,
            ],
        )'''
    if old_change_out in text:
        text = text.replace(old_change_out, new_change_out, 1)

    old_clear_out = '''        file_input.clear(
            on_file_clear,
            inputs=[file_input, state],
            outputs=[
                result_file_selector,
                state,
                uploaded_files_view,
                preview,  # Clear preview
                output_file_mono,  # Clear mono download
                output_file_dual,  # Clear dual download
                output_file_glossary,  # Clear glossary download
                output_file_mono,  # Hide mono button visibility
                output_file_dual,  # Hide dual button visibility
                output_file_glossary,  # Hide glossary button visibility
            ],
        )'''
    # on_file_clear likely returns 10 values without html - need to check and patch function too
    # For clear, add a wrapper or patch return. Simpler: use a lambda wrapper.
    new_clear_out = '''        def _qy_on_file_clear(files, state):
            outs = on_file_clear(files, state)
            return (*outs, gr.update(value="", visible=False))

        file_input.clear(
            _qy_on_file_clear,
            inputs=[file_input, state],
            outputs=[
                result_file_selector,
                state,
                uploaded_files_view,
                preview,  # Clear preview
                output_file_mono,  # Clear mono download
                output_file_dual,  # Clear dual download
                output_file_glossary,  # Clear glossary download
                output_file_mono,  # Hide mono button visibility
                output_file_dual,  # Hide dual button visibility
                output_file_glossary,  # Hide glossary button visibility
                preview_html,
            ],
        )'''
    if "_qy_on_file_clear" not in text and old_clear_out in text:
        text = text.replace(old_clear_out, new_clear_out, 1)

    # safe_update_preview empty + selector outputs
    old_safe_empty = '''                preview_results = update_preview(corrected_label, state) if corrected_label else (
                    None, None, None, None,
                    gr.update(visible=False), gr.update(visible=False), gr.update(visible=False)
                )'''
    new_safe_empty = '''                preview_results = update_preview(corrected_label, state) if corrected_label else (
                    None, None, None, None,
                    gr.update(visible=False), gr.update(visible=False), gr.update(visible=False),
                    gr.update(value="", visible=False),
                )'''
    if old_safe_empty in text:
        text = text.replace(old_safe_empty, new_safe_empty, 1)

    old_sel_out = '''        result_file_selector.change(
            safe_update_preview,
            inputs=[result_file_selector, state],
            outputs=[
                output_file_mono,  # Mono PDF file
                preview,  # Preview
                output_file_dual,  # Dual PDF file
                output_file_glossary,
                output_file_mono,  # Visibility of mono output
                output_file_dual,  # Visibility of dual output
                output_file_glossary,
                result_file_selector,  # Fix selector if value is invalid
            ],
        )'''
    new_sel_out = '''        result_file_selector.change(
            safe_update_preview,
            inputs=[result_file_selector, state],
            outputs=[
                output_file_mono,  # Mono PDF file
                preview,  # Preview
                output_file_dual,  # Dual PDF file
                output_file_glossary,
                output_file_mono,  # Visibility of mono output
                output_file_dual,  # Visibility of dual output
                output_file_glossary,
                preview_html,
                result_file_selector,  # Fix selector if value is invalid
            ],
        )'''
    if old_sel_out in text:
        # safe_update_preview returns (*preview_results, selector_update)
        # preview_results now has 8 items, so selector is last — outputs need preview_html before selector
        text = text.replace(old_sel_out, new_sel_out, 1)

    # 插入 hook：放在 downloads.then 完整闭合之后
    then_marker = "_qy_office_preview_then"
    if then_marker not in text:
        hook = '''
        # _qy_office_preview_then
        def _qy_refresh_office_preview(selected_label, state):
            outs = update_preview(selected_label, state) if selected_label else (
                None, None, None, None,
                gr.update(visible=False), gr.update(visible=False), gr.update(visible=False),
                gr.update(value="", visible=False),
            )
            return outs[1], outs[7]

        _qy_translate_evt.then(
            _qy_refresh_office_preview,
            inputs=[result_file_selector, state],
            outputs=[preview, preview_html],
        )
'''
        anchor = "        # ADDED: Handle result selector change\n"
        if anchor not in text:
            raise RuntimeError("找不到 result selector 锚点")
        text = text.replace(anchor, hook + "\n" + anchor, 1)

    # 若 update_preview 仍是旧版（未含 PLAN-014），用宽松标记替换 return 块
    if "PLAN-014: non-PDF" not in text and "_qy_preview_payload(preview_path)" not in text:
        raise RuntimeError(
            "update_preview 未打上 PLAN-014；请检查空白差异后手动对齐"
        )

    # 升级：非 PDF 时隐藏 PDF()，避免空壳占 75vh
    if "def _qy_hide_pdf(" not in text:
        text = text.replace(
            "def _qy_preview_payload(path_str: str | None) -> tuple:\n"
            '    """返回 (pdf_path_or_none, html_update)。"""\n',
            "def _qy_hide_pdf():\n"
            "    return gr.update(value=None, visible=False)\n"
            "\n"
            "\n"
            "def _qy_show_pdf(path: str):\n"
            "    return gr.update(value=path, visible=True)\n"
            "\n"
            "\n"
            "def _qy_preview_payload(path_str: str | None) -> tuple:\n"
            '    """返回 (pdf_update, html_update)。非 PDF 必须隐藏 PDF()，否则空壳占 75vh。"""\n',
            1,
        )
        text = text.replace(
            "        return None, gr.update(value=\"\", visible=False)\n",
            "        return _qy_hide_pdf(), gr.update(value=\"\", visible=False)\n",
        )
        text = text.replace(
            "        return None, gr.update(\n"
            "            value=_qy_wrap_preview_html(f\"<p>文件不存在：{path.name}</p>\"),\n"
            "            visible=True,\n"
            "        )\n",
            "        return _qy_hide_pdf(), gr.update(\n"
            "            value=_qy_wrap_preview_html(f\"<p>文件不存在：{path.name}</p>\"),\n"
            "            visible=True,\n"
            "        )\n",
        )
        text = text.replace(
            '        return str(path), gr.update(value="", visible=False)\n',
            '        return _qy_show_pdf(str(path)), gr.update(value="", visible=False)\n',
        )
        text = text.replace(
            "            return None, gr.update(value=_qy_wrap_preview_html(body, path.name), visible=True)\n",
            "            return _qy_hide_pdf(), gr.update(value=_qy_wrap_preview_html(body, path.name), visible=True)\n",
        )
        text = text.replace(
            "    return None, gr.update(value=_qy_wrap_preview_html(body, path.name), visible=True)\n",
            "    return _qy_hide_pdf(), gr.update(value=_qy_wrap_preview_html(body, path.name), visible=True)\n",
        )
        text = text.replace(
            "    empty_html = gr.update(value=\"\", visible=False)\n"
            "    # 1. Basic validation\n",
            "    empty_html = gr.update(value=\"\", visible=False)\n"
            "    hide_pdf = gr.update(value=None, visible=False)\n"
            "    # 1. Basic validation\n",
            1,
        )
        text = text.replace(
            "            None,\n"
            "            None,\n"
            "            None,\n"
            "            None,\n"
            "            gr.update(visible=False),\n"
            "            gr.update(visible=False),\n"
            "            gr.update(visible=False),\n"
            "            empty_html,\n",
            "            None,\n"
            "            hide_pdf,\n"
            "            None,\n"
            "            None,\n"
            "            gr.update(visible=False),\n"
            "            gr.update(visible=False),\n"
            "            gr.update(visible=False),\n"
            "            empty_html,\n",
        )

    hide_empty_css = (
        "    .pdf-preview-fixed:not(:has(canvas)):not(:has(iframe)):not(:has(embed)) {"
    )
    if hide_empty_css not in text:
        text = text.replace(
            "    .qy-html-preview-wrap {\n",
            "    .qy-html-preview-wrap {\n",
            1,
        )
        text = text.replace(
            """    .qy-html-preview-wrap {
        max-height: min(70vh, 820px);
        overflow: auto;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        background: #fff;
        padding: 12px 16px;
    }""",
            """    .qy-html-preview-wrap {
        max-height: min(70vh, 820px);
        overflow: auto;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        background: #fff;
        padding: 12px 16px;
    }
    .pdf-preview-fixed:not(:has(canvas)):not(:has(iframe)):not(:has(embed)) {
        display: none !important;
        height: 0 !important;
        max-height: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
        overflow: hidden !important;
        border: none !important;
    }""",
            1,
        )

    skip_marker = "# PLAN-014: don't feed non-PDF into PDF()"
    if skip_marker not in text:
        old = '''        if preview_file_key:
            preview_path = state["display_map"].get(preview_file_key)
            parent_key = state["parent_map"].get(preview_file_key)
            if parent_key and parent_key in state["results"]:
                current_res = state["results"][parent_key]'''
        new = '''        if preview_file_key:
            preview_path = state["display_map"].get(preview_file_key)
            parent_key = state["parent_map"].get(preview_file_key)
            if parent_key and parent_key in state["results"]:
                current_res = state["results"][parent_key]
            # PLAN-014: don't feed non-PDF into PDF()
            if preview_path and not str(preview_path).lower().endswith(".pdf"):
                preview_path = None'''
        if old in text:
            text = text.replace(old, new, 1)

    return text


def main() -> int:
    if not GUI.is_file():
        print(f"找不到 {GUI}", file=sys.stderr)
        return 1
    original = GUI.read_text(encoding="utf-8")
    try:
        updated = apply(original)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    if updated == original:
        print("already patched:", GUI)
        return 0
    GUI.write_text(updated, encoding="utf-8")
    print("patched:", GUI)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
