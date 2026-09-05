#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""精简 pdf2zh Gradio 下载区：仅译稿 / 原文+译稿 + PDF/MD/DOCX。uv 升级后重跑。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)
YAML = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui_translation.yaml"
)
MARKER = "_qy_downloads_ui"


OLD_DOWNLOAD_BLOCK = '''                            # 主界面左侧保留翻译按钮和已翻译下载区
                            output_title = gr.Markdown(_("## Translated"), visible=False)
                            output_file_mono = gr.File(
                                label=_("Download Translation (Mono)"), visible=False
                            )
                            output_file_dual = gr.File(
                                label=_("Download Translation (Dual)"), visible=False
                            )
                            output_file_glossary = gr.File(
                                label=_("Download automatically extracted glossary"),
                                visible=False,
                            )
                            output_file_zip = gr.File(
                                label=_("Download All (ZIP)"), visible=False
                            )
                            output_file_zip_mono = gr.File(
                                label=_("Download All Mono (ZIP)"), visible=False
                            )
                            output_file_zip_dual = gr.File(
                                label=_("Download All Dual (ZIP)"), visible=False
                            )
                            output_file_zip_glossary = gr.File(
                                label=_("Download All Glossaries (ZIP)"), visible=False
                            )'''

NEW_DOWNLOAD_BLOCK = '''                            # 主界面左侧保留翻译按钮和已翻译下载区
                            # _qy_downloads_ui
                            output_title = gr.Markdown(_("## Translated"), visible=False)
                            download_content_mode = gr.Radio(
                                label=_("Download content"),
                                choices=[
                                    _("Translation only"),
                                    _("Original + Translation"),
                                ],
                                value=_("Translation only"),
                                visible=False,
                            )
                            download_formats = gr.CheckboxGroup(
                                label=_("Export formats"),
                                choices=["PDF", "Markdown", "DOCX"],
                                value=["PDF"],
                                visible=False,
                            )
                            download_format_hint = gr.Markdown(
                                _("Markdown/DOCX require extra parsing and translation."),
                                visible=False,
                            )
                            output_file_mono = gr.File(
                                label=_("Download Translation"), visible=False
                            )
                            output_file_dual = gr.File(
                                label=_("Download Original + Translation"), visible=False
                            )
                            output_file_md = gr.File(
                                label=_("Download Markdown"), visible=False
                            )
                            output_file_docx = gr.File(
                                label=_("Download DOCX"), visible=False
                            )
                            output_file_glossary = gr.File(
                                label=_("Download automatically extracted glossary"),
                                visible=False,
                            )
                            with gr.Accordion(_("Batch download (ZIP)"), open=False, visible=False) as zip_accordion:
                                output_file_zip = gr.File(
                                    label=_("Download All (ZIP)"), visible=False
                                )
                                output_file_zip_mono = gr.File(
                                    label=_("Download All Mono (ZIP)"), visible=False
                                )
                                output_file_zip_dual = gr.File(
                                    label=_("Download All Dual (ZIP)"), visible=False
                                )
                                output_file_zip_glossary = gr.File(
                                    label=_("Download All Glossaries (ZIP)"), visible=False
                                )'''

HOOK_MARKER = "_qy_downloads_hook"

HOOK_CODE = '''
        # _qy_downloads_hook
        def _qy_apply_download_prefs(content_mode, formats, mono_path, dual_path, md_path, docx_path, zip_vis=False):
            fmts = formats or ["PDF"]
            want_pdf = "PDF" in fmts
            want_md = "Markdown" in fmts
            want_docx = "DOCX" in fmts
            only = (content_mode or "").startswith("仅") or (content_mode or "") == _("Translation only")
            hint_vis = want_md or want_docx
            dual_or_mono = dual_path or mono_path
            return (
                gr.update(visible=True),  # content mode
                gr.update(visible=True),  # formats
                gr.update(visible=hint_vis),  # hint
                gr.update(visible=bool(want_pdf and only and mono_path), value=mono_path if (want_pdf and only) else None),
                gr.update(visible=bool(want_pdf and (not only) and dual_or_mono), value=dual_or_mono if (want_pdf and not only) else None),
                gr.update(visible=bool(want_md and md_path), value=md_path if want_md else None),
                gr.update(visible=bool(want_docx and docx_path), value=docx_path if want_docx else None),
                gr.update(visible=bool(zip_vis)),  # accordion
            )

        def _qy_export_after_translate(content_mode, formats, state, mono_path, dual_path):
            import sys as _qy_sys
            from pathlib import Path as _qy_Path
            _qy_scripts = _qy_Path("/home/dev/qyunslation/scripts")
            if str(_qy_scripts) not in _qy_sys.path:
                _qy_sys.path.insert(0, str(_qy_scripts))
            fmts = formats or ["PDF"]
            want_md = "Markdown" in fmts
            want_docx = "DOCX" in fmts
            md_path = None
            docx_path = None
            session_id = (state or {}).get("session_id")
            if (want_md or want_docx) and session_id:
                session_dir = _qy_Path("pdf2zh_files") / session_id
                stem = ""
                order = (state or {}).get("file_order") or []
                if order:
                    stem = _qy_Path(order[-1]).stem
                try:
                    from export_md_docx import export_formats as _qy_export
                    out = _qy_export(
                        session_dir=session_dir,
                        stem=stem or "document",
                        want_md=want_md,
                        want_docx=want_docx,
                    )
                    md_path = str(out["md"]) if out.get("md") else None
                    docx_path = str(out["docx"]) if out.get("docx") else None
                except Exception as _qy_exc:
                    import logging as _qy_log
                    _qy_log.getLogger(__name__).warning("md/docx export failed: %s", _qy_exc)
            n_files = len((state or {}).get("file_order") or [])
            return _qy_apply_download_prefs(
                content_mode, formats, mono_path, dual_path, md_path, docx_path, zip_vis=n_files > 1
            )

        download_content_mode.change(
            lambda m, f, mono, dual, md, docx: _qy_apply_download_prefs(m, f, mono, dual, md, docx),
            inputs=[download_content_mode, download_formats, output_file_mono, output_file_dual, output_file_md, output_file_docx],
            outputs=[download_content_mode, download_formats, download_format_hint, output_file_mono, output_file_dual, output_file_md, output_file_docx, zip_accordion],
        )
        download_formats.change(
            lambda m, f, mono, dual, md, docx: _qy_apply_download_prefs(m, f, mono, dual, md, docx),
            inputs=[download_content_mode, download_formats, output_file_mono, output_file_dual, output_file_md, output_file_docx],
            outputs=[download_content_mode, download_formats, download_format_hint, output_file_mono, output_file_dual, output_file_md, output_file_docx, zip_accordion],
        )
'''

THEN_ANCHOR = '''        translate_btn.click(
            translate_files,  # MODIFIED function name
            inputs=[
                file_type,
                file_input,
                link_input,
                *ui_setting_controls,
            ],
            outputs=[
                output_file_mono,  # Mono PDF file
                preview,  # Preview
                output_file_dual,  # Dual PDF file
                output_file_glossary,
                output_file_mono,  # Visibility of mono output
                output_file_dual,  # Visibility of dual output
                output_file_glossary,
                output_title,  # Visibility of output title
                result_file_selector,  # Result selector
                result_file_selector,  # Visibility
                output_file_zip,  # Visibility
                output_file_zip,  # Zip File
                output_file_zip_mono,  # Visibility
                output_file_zip_mono,  # File
                output_file_zip_dual,  # Visibility
                output_file_zip_dual,  # File
                output_file_zip_glossary,  # Visibility
                output_file_zip_glossary,  # File
                uploaded_files_view,  # Uploaded files view
            ],
            show_progress_on=[preview],
        )'''

THEN_REPLACEMENT = '''        _qy_translate_evt = translate_btn.click(
            translate_files,  # MODIFIED function name
            inputs=[
                file_type,
                file_input,
                link_input,
                *ui_setting_controls,
            ],
            outputs=[
                output_file_mono,  # Mono PDF file
                preview,  # Preview
                output_file_dual,  # Dual PDF file
                output_file_glossary,
                output_file_mono,  # Visibility of mono output
                output_file_dual,  # Visibility of dual output
                output_file_glossary,
                output_title,  # Visibility of output title
                result_file_selector,  # Result selector
                result_file_selector,  # Visibility
                output_file_zip,  # Visibility
                output_file_zip,  # Zip File
                output_file_zip_mono,  # Visibility
                output_file_zip_mono,  # File
                output_file_zip_dual,  # Visibility
                output_file_zip_dual,  # File
                output_file_zip_glossary,  # Visibility
                output_file_zip_glossary,  # File
                uploaded_files_view,  # Uploaded files view
            ],
            show_progress_on=[preview],
        )
        # _qy_downloads_then
        _qy_translate_evt.then(
            _qy_export_after_translate,
            inputs=[download_content_mode, download_formats, state, output_file_mono, output_file_dual],
            outputs=[
                download_content_mode,
                download_formats,
                download_format_hint,
                output_file_mono,
                output_file_dual,
                output_file_md,
                output_file_docx,
                zip_accordion,
            ],
        )'''

ZH_KEYS = {
    "Download content": "下载内容",
    "Translation only": "仅译稿",
    "Original + Translation": "原文 + 译稿",
    "Export formats": "导出格式",
    "Markdown/DOCX require extra parsing and translation.": "勾选 Markdown/DOCX 需额外解析翻译，耗时较长。",
    "Download Translation": "下载译稿",
    "Download Original + Translation": "下载原文 + 译稿",
    "Download Markdown": "下载 Markdown",
    "Download DOCX": "下载 DOCX",
    "Batch download (ZIP)": "批量下载（ZIP）",
    "Download All (ZIP)": "全部下载（ZIP）",
    "Download All Mono (ZIP)": "全部译稿（ZIP）",
    "Download All Dual (ZIP)": "全部双语（ZIP）",
    "Download All Glossaries (ZIP)": "全部术语表（ZIP）",
}


def patch_yaml(text: str) -> str:
    # Insert under zh: block after Download Translation (Mono) line if missing
    if "Download content:" in text and "下载内容" in text:
        return text
    zh_mono = "  Download Translation (Mono): 下载翻译（单语版）\n"
    extra = "".join(f"  {k}: {v}\n" for k, v in ZH_KEYS.items())
    if zh_mono in text:
        # only inject once in zh section — find zh: then first occurrence after it
        idx = text.find("\nzh:\n")
        if idx < 0:
            return text
        sub = text[idx:]
        pos = sub.find(zh_mono)
        if pos < 0:
            return text
        insert_at = idx + pos + len(zh_mono)
        return text[:insert_at] + extra + text[insert_at:]
    return text


def apply(text: str) -> str:
    if OLD_DOWNLOAD_BLOCK in text:
        text = text.replace(OLD_DOWNLOAD_BLOCK, NEW_DOWNLOAD_BLOCK, 1)
    elif MARKER not in text:
        raise RuntimeError("找不到下载区锚点，gui.py 可能已升级")

    if HOOK_MARKER not in text:
        # inject hooks before translate_btn.click
        anchor = "        # Translation button click handler\n"
        if anchor not in text:
            raise RuntimeError("找不到 translate 按钮锚点")
        text = text.replace(anchor, HOOK_CODE + "\n" + anchor, 1)
    else:
        # 幂等升级：letter 无 dual 时回退 mono
        text = text.replace(
            "gr.update(visible=bool(want_pdf and (not only) and dual_path), value=dual_path if (want_pdf and not only) else None),",
            "gr.update(visible=bool(want_pdf and (not only) and dual_or_mono), value=dual_or_mono if (want_pdf and not only) else None),",
        )
        if "dual_or_mono = dual_path or mono_path" not in text:
            text = text.replace(
                "            hint_vis = want_md or want_docx\n",
                "            hint_vis = want_md or want_docx\n"
                "            dual_or_mono = dual_path or mono_path\n",
                1,
            )

    if "_qy_downloads_then" not in text:
        if THEN_ANCHOR not in text:
            raise RuntimeError("找不到 translate_btn.click 块")
        text = text.replace(THEN_ANCHOR, THEN_REPLACEMENT, 1)
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
    if updated != original:
        GUI.write_text(updated, encoding="utf-8")
        print(f"已写入 {GUI}")
    else:
        print("gui.py 已是 downloads 补丁")

    if YAML.is_file():
        y0 = YAML.read_text(encoding="utf-8")
        y1 = patch_yaml(y0)
        if y1 != y0:
            YAML.write_text(y1, encoding="utf-8")
            print(f"已写入 {YAML}")
        else:
            print("yaml 已含中文下载文案")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
