#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-017：双预览 2:4:4 布局 + 进度槽位 + 行内页脚。

须在 apply-pdf2zh-settings-inline.py / office-preview 之后执行。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)

MARKER = "_qy_dual_preview"
CSS_MARKER = "/* _qy_dual_preview_css */"
PAYLOAD_MARKER = "def _qy_dual_payload("

RIGHT_OLD = '''                        with gr.Column(scale=2, elem_classes=["qy-col-right"]):
                            gr.Markdown(_("## Preview"), elem_classes=["tab-title"])
                            # 结果选择 + 预览
                            result_file_selector = gr.Dropdown(
                                label=_("Select File to Preview/Download"),
                                choices=[],
                                value=None,
                                visible=True,
                                interactive=True,
                            )
                            # 预览区域上方已经有“## Preview”标题，这里关闭组件自带 label，
                            # 避免 Gradio 的标签卡片在布局调整后漂到左侧中间
                            preview = PDF(
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
                            )
'''

MID_RIGHT_NEW = '''                        # _qy_dual_preview
                        with gr.Column(scale=4, elem_classes=["qy-col-mid"]):
                            gr.Markdown("## 原文", elem_classes=["tab-title"])
                            result_file_selector = gr.Dropdown(
                                label="当前文档",
                                choices=[],
                                value=None,
                                visible=True,
                                interactive=True,
                            )
                            preview_src = PDF(
                                label=None,
                                show_label=False,
                                visible=True,
                                elem_classes=["pdf-preview-fixed", "qy-preview-src"],
                            )
                            preview_src_html = gr.HTML(
                                value="",
                                visible=False,
                                elem_classes=["qy-html-preview-wrap", "qy-preview-src-html"],
                            )

                        with gr.Column(scale=4, elem_classes=["qy-col-right"]):
                            gr.Markdown("## 译文", elem_classes=["tab-title"])
                            preview = PDF(
                                label=None,
                                show_label=False,
                                visible=True,
                                elem_classes=["pdf-preview-fixed", "qy-preview-dst"],
                            )
                            # _qy_office_preview
                            preview_html = gr.HTML(
                                value="",
                                visible=False,
                                elem_classes=["qy-html-preview-wrap", "qy-preview-dst-html"],
                            )
                            qy_progress_slot = gr.HTML(
                                value="",
                                visible=True,
                                elem_classes=["qy-progress-slot"],
                            )
'''

FOOTER_ROW = '''
                    # _qy_dual_preview_footer
                    with gr.Row(elem_classes=["qy-inline-footer-row"]):
                        with gr.Column(scale=2, elem_classes=["qy-footer-spacer"]):
                            gr.HTML("")
                        with gr.Column(scale=8, elem_classes=["qy-inline-footer-col"]):
                            gr.HTML(
                                '<div class="qy-inline-footer">'
                                '<img src="/gradio_api/file=/home/dev/pdf2zh/brand/quanxin-logo.svg" alt="QYuns">'
                                "<span>Qyunslation · 荃信生物 © 2026</span>"
                                "</div>"
                            )
'''

DUAL_PAYLOAD_FN = '''
def _qy_dual_payload(selected_label, state):
    """返回 (src_pdf, src_html, dst_pdf, dst_html)。单选择器驱动中栏原文 + 右栏译文。"""
    empty_html = gr.update(value="", visible=False)
    hide_pdf = gr.update(value=None, visible=False)
    if not selected_label or not state:
        return hide_pdf, empty_html, hide_pdf, empty_html
    dm = state.get("display_map") or {}
    pm = state.get("parent_map") or {}
    parent = pm.get(selected_label, selected_label)
    src = dm.get(parent)
    if selected_label != parent and selected_label in dm:
        dst = dm.get(selected_label)
    else:
        res = (state.get("results") or {}).get(parent) or {}
        dst = res.get("mono") or res.get("dual")
    return (*_qy_preview_payload(src), *_qy_preview_payload(dst))

'''

CSS_BLOCK = """
    /* _qy_dual_preview_css */
    :root { --qy-footer-h: 0px !important; }
    .sidebar-nav {
        display: none !important;
        width: 0 !important;
        min-width: 0 !important;
        max-width: 0 !important;
        overflow: hidden !important;
        padding: 0 !important;
        margin: 0 !important;
        border: none !important;
    }
    .qy-page-footer {
        display: none !important;
        height: 0 !important;
        max-height: 0 !important;
        overflow: hidden !important;
        visibility: hidden !important;
        pointer-events: none !important;
        position: static !important;
    }
    .qy-col-mid {
        height: 100% !important;
        min-height: 0 !important;
        display: flex !important;
        flex-direction: column !important;
        gap: 8px !important;
    }
    .qy-col-mid > * { flex: 0 0 auto !important; }
    .qy-col-mid > .pdf-preview-fixed.hidden,
    .qy-col-mid > .qy-html-preview-wrap.hidden {
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
    .qy-col-mid > .qy-html-preview-wrap:not(.hidden) {
        flex: 1 1 auto !important;
        min-height: 0 !important;
        height: auto !important;
        max-height: none !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 10px !important;
        overflow: auto !important;
    }
    .qy-col-right > .pdf-preview-fixed:not(.hidden):has(canvas),
    .qy-col-right > .pdf-preview-fixed:not(.hidden):has(iframe),
    .qy-col-right > .pdf-preview-fixed:not(.hidden):has(embed),
    .qy-col-right > .qy-html-preview-wrap:not(.hidden) {
        border: 1px solid #e2e8f0 !important;
        border-radius: 10px !important;
        order: 5 !important;
    }
    .qy-col-mid::after {
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
    }
    .qy-col-mid:has(> .pdf-preview-fixed:not(.hidden):has(canvas))::after,
    .qy-col-mid:has(> .pdf-preview-fixed:not(.hidden):has(iframe))::after,
    .qy-col-mid:has(> .pdf-preview-fixed:not(.hidden):has(embed))::after,
    .qy-col-mid:has(> .qy-html-preview-wrap:not(.hidden))::after {
        display: none !important;
    }
    .qy-col-right::after {
        content: "翻译完成后在此显示译文" !important;
        order: 10 !important;
    }
    .qy-progress-slot {
        flex: 0 0 40px !important;
        order: 20 !important;
        min-height: 40px !important;
        max-height: 48px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        border: 1px dashed #e2e8f0 !important;
        border-radius: 8px !important;
        background: #f8fafc !important;
        color: #64748b !important;
        font-size: 0.85rem !important;
        overflow: hidden !important;
    }
    .qy-progress-slot .progress-text,
    .qy-progress-slot .meta-text,
    .qy-progress-slot .progress-bar,
    .qy-progress-slot .wrap {
        width: 100% !important;
    }
    .qy-inline-footer-row {
        flex: 0 0 auto !important;
        min-height: 34px !important;
        max-height: 36px !important;
        margin-top: 4px !important;
        align-items: center !important;
        padding: 0 20px 4px 4px !important;
    }
    .qy-footer-spacer { min-height: 0 !important; }
    .qy-inline-footer-col {
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        min-height: 0 !important;
    }
    .qy-inline-footer {
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 8px !important;
        width: 100% !important;
        color: #94a3b8 !important;
        font-size: 0.8rem !important;
        border-top: 1px solid #eef2f7 !important;
        padding-top: 6px !important;
    }
    .qy-inline-footer img {
        height: 16px !important;
        width: auto !important;
        max-width: 120px !important;
        object-fit: contain !important;
    }
"""


def _replace_once(text: str, old: str, new: str, label: str) -> tuple[str, bool]:
    if new.strip()[:40] in text and old not in text:
        return text, False
    if old not in text:
        print(f"WARNING: {label} anchor missing", file=sys.stderr)
        return text, False
    return text.replace(old, new, 1), True


def apply_skeleton(text: str) -> tuple[str, bool]:
    changed = False
    if 'elem_classes=["qy-col-left"]' in text and "scale=2, elem_classes=[\"qy-col-left\"]" not in text:
        text2, ok = _replace_once(
            text,
            'with gr.Column(scale=1, elem_classes=["qy-col-left"]):',
            'with gr.Column(scale=2, elem_classes=["qy-col-left"]):',
            "left scale",
        )
        text, changed = text2, changed or ok

    if MARKER not in text or "preview_src = PDF" not in text:
        text2, ok = _replace_once(text, RIGHT_OLD, MID_RIGHT_NEW, "mid/right columns")
        text, changed = text2, changed or ok

    # Remove ## File(s) title
    file_title = '                            gr.Markdown(_("## File(s)"), elem_classes=["tab-title"])\n'
    if file_title in text:
        text = text.replace(file_title, "                            # _qy_dual_preview: File(s) title removed\n", 1)
        changed = True

    # file_input show_label=False
    old_fi = '''                            file_input = gr.File(
                                label=_("File(s)"),
                                file_count="multiple",
                                file_types=[".pdf", ".PDF", ".doc", ".docx", ".png", ".jpg", ".jpeg"],
                                type="filepath",
                                elem_classes=["input-file"],
                            )
'''
    new_fi = '''                            file_input = gr.File(
                                label=_("File(s)"),
                                show_label=False,
                                file_count="multiple",
                                file_types=[".pdf", ".PDF", ".doc", ".docx", ".png", ".jpg", ".jpeg"],
                                type="filepath",
                                elem_classes=["input-file"],
                            )
'''
    if "show_label=False" not in text[text.find("file_input = gr.File") : text.find("file_input = gr.File") + 350]:
        if old_fi in text:
            text = text.replace(old_fi, new_fi, 1)
            changed = True

    return text, changed


def apply_footer(text: str) -> tuple[str, bool]:
    if "_qy_dual_preview_footer" in text:
        return text, False
    # Insert after main inner row closes, before tab_settings
    # Find the closing of right column / inner row: look for settings-container after dual marker
    anchor = (
        "                # 其余高级配置都移动到设置页\n"
        '                with gr.Group(visible=False, elem_classes=["settings-container"]) as tab_settings:\n'
    )
    if anchor not in text:
        print("WARNING: footer insert anchor missing", file=sys.stderr)
        return text, False
    return text.replace(anchor, FOOTER_ROW + "\n" + anchor, 1), True


def apply_payload_fn(text: str) -> tuple[str, bool]:
    if PAYLOAD_MARKER in text:
        return text, False
    # Insert after _qy_preview_payload function ends — before update_preview
    anchor = "def update_preview(selected_label, state):"
    if anchor not in text:
        print("WARNING: update_preview anchor missing", file=sys.stderr)
        return text, False
    return text.replace(anchor, DUAL_PAYLOAD_FN + anchor, 1), True


def apply_progress_bind(text: str) -> tuple[str, bool]:
    old = "show_progress_on=[preview, preview_html],"
    new = "show_progress_on=[qy_progress_slot],"
    if new in text:
        return text, False
    if old not in text:
        # maybe already only preview
        old2 = "show_progress_on=[preview],"
        if old2 in text:
            return text.replace(old2, new, 1), True
        print("WARNING: show_progress_on anchor missing", file=sys.stderr)
        return text, False
    return text.replace(old, new, 1), True


def apply_refresh_then(text: str) -> tuple[str, bool]:
    old = '''        # _qy_office_preview_then
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
    new = '''        # _qy_office_preview_then
        # _qy_dual_preview_refresh
        def _qy_refresh_office_preview(selected_label, state):
            return _qy_dual_payload(selected_label, state)

        _qy_translate_evt.then(
            _qy_refresh_office_preview,
            inputs=[result_file_selector, state],
            outputs=[preview_src, preview_src_html, preview, preview_html],
        )
'''
    if "_qy_dual_preview_refresh" in text and "preview_src, preview_src_html, preview, preview_html" in text:
        return text, False
    if old not in text:
        # try if already partially patched
        if "def _qy_refresh_office_preview" in text and "preview_src" not in text.split("def _qy_refresh_office_preview", 1)[1][:500]:
            # replace function body loosely
            pat = re.compile(
                r"        # _qy_office_preview_then\n"
                r"        def _qy_refresh_office_preview\(selected_label, state\):.*?"
                r"        _qy_translate_evt\.then\(\n"
                r"            _qy_refresh_office_preview,\n"
                r"            inputs=\[result_file_selector, state\],\n"
                r"            outputs=\[preview, preview_html\],\n"
                r"        )\n",
                re.S,
            )
            if pat.search(text):
                text = pat.sub(new, text, count=1)
                return text, True
        print("WARNING: refresh then block missing", file=sys.stderr)
        return text, False
    return text.replace(old, new, 1), True


def apply_selector_change(text: str) -> tuple[str, bool]:
    if "_qy_dual_safe_update" in text:
        return text, False
    old = '''        # ADDED: Handle result selector change
        def safe_update_preview(selected_label, state):
            """
            Wrapper for update_preview that ensures selected_label is valid before processing.
            Also returns an update for result_file_selector if the value needs to be corrected.
            """
            # Validate selected_label is in choices
            if not state or "display_map" not in state:
                choices = []
            else:
                choices = list(state.get("display_map", {}).keys())
            
            # If selected_label is not in choices, reset it
            if selected_label and selected_label not in choices:
                # Reset to first available choice or None
                corrected_label = choices[0] if choices else None
                # Return preview update + selector update
                preview_results = update_preview(corrected_label, state) if corrected_label else (
                    None, None, None, None,
                    gr.update(visible=False), gr.update(visible=False), gr.update(visible=False),
                    gr.update(value="", visible=False),
                )
                return (
                    *preview_results,
                    gr.update(choices=choices, value=corrected_label, visible=bool(choices)),  # Fix selector
                )
            else:
                # Normal case: selected_label is valid
                preview_results = update_preview(selected_label, state)
                return (
                    *preview_results,
                    gr.update(),  # No change to selector
                )

        result_file_selector.change(
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
        )
'''
    new = '''        # ADDED: Handle result selector change
        # _qy_dual_safe_update
        def safe_update_preview(selected_label, state):
            """
            Wrapper for update_preview that ensures selected_label is valid before processing.
            Also returns an update for result_file_selector if the value needs to be corrected.
            PLAN-017: also refresh mid (source) + right (dest) panes.
            """
            if not state or "display_map" not in state:
                choices = []
            else:
                choices = list(state.get("display_map", {}).keys())

            if selected_label and selected_label not in choices:
                corrected_label = choices[0] if choices else None
                preview_results = update_preview(corrected_label, state) if corrected_label else (
                    None, None, None, None,
                    gr.update(visible=False), gr.update(visible=False), gr.update(visible=False),
                    gr.update(value="", visible=False),
                )
                src_pdf, src_html, dst_pdf, dst_html = _qy_dual_payload(corrected_label, state)
                # Replace single preview slots with dest; append source panes
                mono, _old_pdf, dual, gloss, vism, visd, visg, _old_html = preview_results
                return (
                    mono, dst_pdf, dual, gloss, vism, visd, visg, dst_html,
                    gr.update(choices=choices, value=corrected_label, visible=bool(choices)),
                    src_pdf, src_html,
                )
            else:
                preview_results = update_preview(selected_label, state)
                src_pdf, src_html, dst_pdf, dst_html = _qy_dual_payload(selected_label, state)
                mono, _old_pdf, dual, gloss, vism, visd, visg, _old_html = preview_results
                return (
                    mono, dst_pdf, dual, gloss, vism, visd, visg, dst_html,
                    gr.update(),
                    src_pdf, src_html,
                )

        result_file_selector.change(
            safe_update_preview,
            inputs=[result_file_selector, state],
            outputs=[
                output_file_mono,  # Mono PDF file
                preview,  # Preview (dest)
                output_file_dual,  # Dual PDF file
                output_file_glossary,
                output_file_mono,  # Visibility of mono output
                output_file_dual,  # Visibility of dual output
                output_file_glossary,
                preview_html,
                result_file_selector,  # Fix selector if value is invalid
                preview_src,
                preview_src_html,
            ],
        )
'''
    if old not in text:
        print("WARNING: safe_update_preview block missing", file=sys.stderr)
        return text, False
    return text.replace(old, new, 1), True


def apply_file_change_clear(text: str) -> tuple[str, bool]:
    changed = False
    if "_qy_wrap_file_change" not in text:
        old_bind = '''        # Handle per-file removal (the small X on each row in the File(s) list)
        file_input.change(
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
        )
'''
        new_bind = '''        # Handle per-file removal (the small X on each row in the File(s) list)
        # _qy_wrap_file_change
        def _qy_wrap_file_change(files, state, selected_label):
            outs = on_file_input_change(files, state, selected_label)
            st = outs[1]
            su = outs[0]
            sel = None
            if isinstance(su, dict):
                sel = su.get("value")
            else:
                sel = getattr(su, "value", None)
            choices = list((st or {}).get("display_map", {}).keys())
            if sel is None and choices:
                sel = choices[0]
            src_pdf, src_html, dst_pdf, dst_html = _qy_dual_payload(sel, st)
            return (
                outs[0], outs[1], outs[2],
                dst_pdf,
                outs[4], outs[5], outs[6], outs[7], outs[8], outs[9],
                dst_html,
                src_pdf, src_html,
            )

        file_input.change(
            _qy_wrap_file_change,
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
                preview_src,
                preview_src_html,
            ],
        )
'''
        if old_bind not in text:
            print("WARNING: file_input.change bind missing", file=sys.stderr)
        else:
            text = text.replace(old_bind, new_bind, 1)
            changed = True

    if "_qy_dual_clear" not in text:
        old_clear = '''        def _qy_on_file_clear(files, state):
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
        )
'''
        new_clear = '''        # _qy_dual_clear
        def _qy_on_file_clear(files, state):
            outs = on_file_clear(files, state)
            empty_html = gr.update(value="", visible=False)
            hide_pdf = gr.update(value=None, visible=False)
            return (*outs, empty_html, hide_pdf, empty_html)

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
                preview_src,
                preview_src_html,
            ],
        )
'''
        if old_clear not in text:
            print("WARNING: file clear bind missing", file=sys.stderr)
        else:
            text = text.replace(old_clear, new_clear, 1)
            changed = True

    # Upload → then dual refresh (selector value set by on_file_upload)
    if "_qy_upload_dual_then" not in text:
        old_up = '''        file_input.upload(
            on_file_upload,
            inputs=[file_input, state],
            outputs=[result_file_selector, state, uploaded_files_view],
        )
'''
        new_up = '''        # _qy_upload_dual_then
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
'''
        if old_up not in text:
            print("WARNING: file upload bind missing", file=sys.stderr)
        else:
            text = text.replace(old_up, new_up, 1)
            changed = True

    return text, changed



def apply_selector_visible(text: str) -> tuple[str, bool]:
    """Keep「当前文档」dropdown always visible (empty choices OK)."""
    changed = False
    reps = [
        (
            "gr.update(choices=all_choices, value=default_value, visible=bool(all_choices))",
            "gr.update(choices=all_choices, value=default_value, visible=True)",
        ),
        (
            "selector_update = gr.update(choices=[], value=None, visible=False)",
            "selector_update = gr.update(choices=[], value=None, visible=True)",
        ),
        (
            "else gr.update(choices=[], value=None, visible=False)",
            "else gr.update(choices=[], value=None, visible=True)",
        ),
        (
            'gr.update(choices=[], value=None, visible=False),\n'
            '            state,\n'
            '            gr.update(value="", visible=False),\n'
            '        )',
            'gr.update(choices=[], value=None, visible=True),\n'
            '            state,\n'
            '            gr.update(value="", visible=False),\n'
            '        )',
        ),
        (
            "return gr.update(choices=[], value=None, visible=False)",
            "return gr.update(choices=[], value=None, visible=True)",
        ),
        (
            "gr.update(choices=choices, value=corrected_label, visible=bool(choices))",
            "gr.update(choices=choices, value=corrected_label, visible=True)",
        ),
        (
            "gr.update(choices=choices, value=selector_value, visible=bool(choices))",
            "gr.update(choices=choices, value=selector_value, visible=True)",
        ),
    ]
    for old, new in reps:
        if old in text:
            text = text.replace(old, new)
            changed = True
    return text, changed


def apply_css(text: str) -> tuple[str, bool]:
    """Always keep dual CSS as the last rules inside custom_css so it wins."""
    original = text
    # Remove any existing dual css blocks
    while CSS_MARKER in text:
        m = re.search(
            r"\n    /\* _qy_dual_preview_css \*/.*?\.qy-inline-footer img \{.*?\n    \}\n",
            text,
            re.S,
        )
        if m:
            text = text[: m.start()] + "\n" + text[m.end() :]
            continue
        # broken remnant (e.g. truncated .qy-col-mid): drop from marker line to closing """
        start = text.find("    /* _qy_dual_preview_css */")
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


def apply(text: str) -> tuple[str, bool]:
    changed = False
    for fn in (
        apply_skeleton,
        apply_footer,
        apply_payload_fn,
        apply_progress_bind,
        apply_refresh_then,
        apply_selector_change,
        apply_file_change_clear,
        apply_selector_visible,
        apply_css,
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

    need(MARKER in text, "marker missing")
    need('scale=2, elem_classes=["qy-col-left"]' in text, "left scale!=2")
    need('scale=4, elem_classes=["qy-col-mid"]' in text, "mid scale missing")
    need('scale=4, elem_classes=["qy-col-right"]' in text, "right scale!=4")
    need(text.count("preview_src = PDF") == 1, f"preview_src defs={text.count('preview_src = PDF')}")
    need(text.count("qy_progress_slot = gr.HTML") == 1, "qy_progress_slot missing")
    need("show_progress_on=[qy_progress_slot]" in text, "progress bind wrong")
    need(PAYLOAD_MARKER in text, "dual payload missing")
    need("_qy_dual_preview_footer" in text, "inline footer missing")
    need(CSS_MARKER in text, "css missing")
    need('gr.Markdown(_("## File(s)")' not in text, "File(s) title still present")
    need("## 原文" in text and "## 译文" in text, "mid/right titles missing")
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
    final = updated if changed else original
    # re-read if we wrote
    if changed:
        final = GUI.read_text(encoding="utf-8")
    errs = verify(final)
    if errs:
        print(f"verify failed: {errs} error(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
