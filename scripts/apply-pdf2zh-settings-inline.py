#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-016：设置项内联左栏 + 取消 ⚙️ 入口。uv 升级后重跑。

硬约束：build_ui_inputs 按位置映射，禁止删除任何控件变量；
只搬迁「有价值」控件到左栏，其余留在永远不可见的 tab_settings。
须在 apply-pdf2zh-docprofile.py / office-preview 之后执行。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)

MARKER = "_qy_settings_inline"
CHANGE_MARKER = "_qy_doc_profile_change"
CSS_MARKER = "/* _qy_settings_inline_css */"

INSERT_ANCHOR = (
    "                            # 主界面左侧保留翻译按钮和已翻译下载区\n"
    "                            # _qy_downloads_ui\n"
)

LEFT_BLOCK = '''                            # _qy_settings_inline
                            doc_profile_dropdown = gr.Dropdown(
                                label="文档类型模板",
                                choices=["自动", "正式书信", "学术文献", "IND递交资料", "通用"],
                                value="自动",
                                interactive=True,
                                allow_custom_value=True,
                            )
                            with gr.Accordion(
                                "高级选项",
                                open=False,
                                elem_classes=["qy-adv-acc"],
                            ):
                                page_range = gr.Radio(
                                    choices=[
                                        ("All", "All"),
                                        ("First", "First"),
                                        ("First 5 pages", "First 5 pages"),
                                        ("Range", "Range"),
                                    ],
                                    label="Pages",
                                    value="All",
                                )
                                page_input = gr.Textbox(
                                    label=_("Page range (e.g., 1,3,5-10,-5)"),
                                    visible=False,
                                    interactive=True,
                                    placeholder=_("e.g., 1,3,5-10"),
                                )
                                only_include_translated_page = gr.Checkbox(
                                    label=_("Only include translated pages in the output PDF."),
                                    info=_("Effective only when a page range is specified."),
                                    value=settings.pdf.only_include_translated_page,
                                    interactive=True,
                                )
                                glossary_file = gr.File(
                                    label=_("Glossary File"),
                                    file_count="multiple",
                                    file_types=[".csv"],
                                    type="binary",
                                    visible=True,
                                )
                                require_llm_translator_inputs.append(glossary_file)
                                ignore_cache = gr.Checkbox(
                                    label=_("Ignore cache"),
                                    value=settings.translation.ignore_cache,
                                    interactive=True,
                                )
                                watermark_output_mode = gr.Radio(
                                    choices=[
                                        ("Watermarked", "Watermarked"),
                                        ("No Watermark", "No Watermark"),
                                    ],
                                    label="Watermark mode",
                                    value="Watermarked"
                                    if settings.pdf.watermark_output_mode == "watermarked"
                                    else "No Watermark",
                                )
                                lang_selector.render()
                                save_btn = gr.Button(
                                    _("Save Settings"),
                                    variant="secondary",
                                    elem_classes=["save-settings-btn"],
                                )

'''

# Original blocks to strip from tab_settings (exact snippets from current gui.py)
PAGE_RANGE_OLD = '''                    page_range = gr.Radio(
                        choices=[
                            ("All", "All"),
                            ("First", "First"),
                            ("First 5 pages", "First 5 pages"),
                            ("Range", "Range"),
                        ],
                        label="Pages",
                        value="All",
                    )

'''

PAGE_INPUT_OLD = '''                    page_input = gr.Textbox(
                    label=_("Page range (e.g., 1,3,5-10,-5)"),
                    visible=False,
                    interactive=True,
                    placeholder=_("e.g., 1,3,5-10"),
                    )

'''

ONLY_INCLUDE_OLD = '''                    only_include_translated_page = gr.Checkbox(
                    label=_("Only include translated pages in the output PDF."),
                    info=_("Effective only when a page range is specified."),
                    value=settings.pdf.only_include_translated_page,
                    interactive=True,
                    )

'''

WATERMARK_OLD = '''                    watermark_output_mode = gr.Radio(
                        choices=[
                            ("Watermarked", "Watermarked"),
                            ("No Watermark", "No Watermark"),
                        ],
                        label="Watermark mode",
                        value="Watermarked"
                        if settings.pdf.watermark_output_mode == "watermarked"
                        else "No Watermark",
                    )

'''

DOC_PROFILE_OLD = '''                        doc_profile_dropdown = gr.Dropdown(
                            label="文档类型模板",
                            choices=["自动", "正式书信", "学术文献", "IND递交资料", "通用"],
                            value="自动",
                            interactive=True,
                            allow_custom_value=True,
                        )

'''

GLOSSARY_FILE_OLD = '''                        glossary_file = gr.File(
                            label=_("Glossary File"),
                            file_count="multiple",
                            file_types=[".csv"],
                            type="binary",
                            visible=True,
                        )
                        require_llm_translator_inputs.append(glossary_file)

'''

IGNORE_CACHE_OLD = '''                        ignore_cache = gr.Checkbox(
                            label=_("Ignore cache"),
                            value=settings.translation.ignore_cache,
                            interactive=True,
                        )

'''

SAVE_BTN_OLD = (
    '                    save_btn = gr.Button(_("Save Settings"), '
    'variant="secondary", elem_classes=["save-settings-btn"])\n'
)

# 必须整行精确匹配（20 空格）；不可用短缩进子串，否则会误伤左栏 32 空格行
LANG_RENDER_OLD = "                    lang_selector.render()\n"
LANG_RENDER_PLACEHOLDER = (
    "                    # _qy_settings_inline: lang_selector.render() moved to left\n"
)
LANG_RENDER_LEFT = "                                lang_selector.render()\n"

SIDEBAR_OLD = (
    '                btn_main_tab = gr.Button("🚀", variant="primary", '
    'elem_classes=["sidebar-btn"])\n'
    '                btn_settings_tab = gr.Button("⚙️", variant="secondary", '
    'elem_classes=["sidebar-btn"])\n'
)
SIDEBAR_NEW = (
    '                btn_main_tab = gr.Button("🚀", variant="primary", '
    'elem_classes=["sidebar-btn"], visible=False)\n'
    '                btn_settings_tab = gr.Button("⚙️", variant="secondary", '
    'elem_classes=["sidebar-btn"], visible=False)\n'
)

CHANGE_HOOK = '''
        # _qy_doc_profile_change
        def _qy_on_doc_profile_change(choice, st):
            st = dict(st or {})
            st["_doc_profile_ui"] = choice
            return st

        doc_profile_dropdown.change(
            _qy_on_doc_profile_change,
            inputs=[doc_profile_dropdown, state],
            outputs=[state],
        )
'''

CSS_BLOCK = """
    /* _qy_settings_inline_css */
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
    .settings-container,
    .settings-container.hide,
    .settings-container:not(.hide) {
        display: none !important;
        height: 0 !important;
        max-height: 0 !important;
        overflow: hidden !important;
        visibility: hidden !important;
        pointer-events: none !important;
    }
    .qy-adv-acc {
        flex: 0 0 auto !important;
        margin-top: 4px !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 10px !important;
        background: #fff !important;
    }
    .qy-adv-acc > .label-wrap,
    .qy-adv-acc .label-wrap {
        padding: 8px 12px !important;
        font-size: 0.9rem !important;
        color: #475569 !important;
    }
"""


def _strip_once(text: str, old: str, label: str) -> tuple[str, bool]:
    if old not in text:
        # Already stripped (placeholder comment) or variant missing
        return text, False
    return text.replace(old, f"                    # _qy_settings_inline: {label} moved to left\n", 1), True


def apply_move(text: str) -> tuple[str, bool]:
    """Insert left block and strip originals. Idempotent via MARKER."""
    changed = False
    if MARKER in text and "doc_profile_dropdown = gr.Dropdown" in text.split(MARKER, 1)[1][:800]:
        # Already inlined
        pass
    else:
        if INSERT_ANCHOR not in text:
            print("ERROR: insert anchor not found", file=sys.stderr)
            return text, False
        if MARKER not in text:
            text = text.replace(INSERT_ANCHOR, LEFT_BLOCK + INSERT_ANCHOR, 1)
            changed = True

    strips = [
        (PAGE_RANGE_OLD, "page_range"),
        (PAGE_INPUT_OLD, "page_input"),
        (ONLY_INCLUDE_OLD, "only_include_translated_page"),
        (WATERMARK_OLD, "watermark_output_mode"),
        (DOC_PROFILE_OLD, "doc_profile_dropdown"),
        (GLOSSARY_FILE_OLD, "glossary_file"),
        (IGNORE_CACHE_OLD, "ignore_cache"),
        (SAVE_BTN_OLD, "save_btn"),
    ]
    for old, label in strips:
        text, did = _strip_once(text, old, label)
        changed = changed or did

    # 设置页 20 空格 render → 占位；若误伤过左栏则恢复
    if LANG_RENDER_OLD in text:
        # 仅替换「独立成行」的设置页 render（行首恰好 20 空格）
        new_text, n = re.subn(
            r"(?m)^                    lang_selector\.render\(\)\n",
            LANG_RENDER_PLACEHOLDER,
            text,
            count=1,
        )
        if n:
            text = new_text
            changed = True
    if (
        "# _qy_settings_inline: lang_selector.render() moved to left" in text
        and LANG_RENDER_LEFT not in text
    ):
        # 恢复左栏 accordion 内的 render（曾被短缩进子串误替换）
        text = text.replace(
            "                                # _qy_settings_inline: lang_selector.render() moved to left\n",
            LANG_RENDER_LEFT,
            1,
        )
        changed = True

    return text, changed


def apply_sidebar(text: str) -> tuple[str, bool]:
    if 'elem_classes=["sidebar-btn"], visible=False)' in text:
        return text, False
    if SIDEBAR_OLD not in text:
        print("WARNING: sidebar buttons not found for hide", file=sys.stderr)
        return text, False
    return text.replace(SIDEBAR_OLD, SIDEBAR_NEW, 1), True


def apply_change_hook(text: str) -> tuple[str, bool]:
    if CHANGE_MARKER in text:
        return text, False
    anchor = """        file_input.upload(
            _qy_hint_doc_profile,
            inputs=[file_input, doc_profile_dropdown, state],
            outputs=[doc_profile_dropdown, state],
        )
"""
    if anchor not in text:
        print("WARNING: doc_profile upload hook anchor missing", file=sys.stderr)
        return text, False
    return text.replace(anchor, anchor + CHANGE_HOOK, 1), True


def apply_css(text: str) -> tuple[str, bool]:
    if CSS_MARKER in text:
        return text, False
    # Append before closing of custom_css / near end of known PLAN-015 footer CSS
    needle = "    .qy-page-footer span {"
    idx = text.find(needle)
    if idx < 0:
        # fallback: inject before first occurrence of '</style>' is not in py; CSS is in string
        # Find last .qy-page-footer block end
        m = re.search(
            r"(    \.qy-page-footer span \{.*?\n    \}\n)",
            text,
            re.S,
        )
        if not m:
            print("WARNING: CSS inject point not found", file=sys.stderr)
            return text, False
        text = text[: m.end()] + CSS_BLOCK + text[m.end() :]
        return text, True
    # find closing brace of that rule
    end = text.find("\n    }", idx)
    if end < 0:
        print("WARNING: CSS rule end not found", file=sys.stderr)
        return text, False
    end = end + len("\n    }\n")
    text = text[:end] + CSS_BLOCK + text[end:]
    return text, True


def apply(text: str) -> tuple[str, bool]:
    changed = False
    text, c = apply_move(text)
    changed = changed or c
    text, c = apply_sidebar(text)
    changed = changed or c
    text, c = apply_change_hook(text)
    changed = changed or c
    text, c = apply_css(text)
    changed = changed or c
    return text, changed


def _count_defs(text: str, name: str) -> int:
    return len(re.findall(rf"^\s*{re.escape(name)}\s*=\s*gr\.", text, re.M))


def verify(text: str) -> int:
    errs = 0
    if MARKER not in text:
        print("ERROR: marker missing", file=sys.stderr)
        errs += 1
    if CHANGE_MARKER not in text:
        print("ERROR: change hook missing", file=sys.stderr)
        errs += 1
    if CSS_MARKER not in text:
        print("ERROR: css missing", file=sys.stderr)
        errs += 1
    for name in (
        "doc_profile_dropdown",
        "page_range",
        "page_input",
        "only_include_translated_page",
        "glossary_file",
        "ignore_cache",
        "watermark_output_mode",
        "save_btn",
    ):
        n = _count_defs(text, name)
        if n != 1:
            print(f"ERROR: {name} defined {n} times (want 1)", file=sys.stderr)
            errs += 1
    # left block must appear before action-row (ignore CSS .action-row)
    left_i = text.find("# _qy_settings_inline\n")
    action_i = text.find('with gr.Row(elem_classes=["action-row"])')
    if left_i < 0 or action_i < 0 or left_i > action_i:
        print("ERROR: left inline block not before action-row", file=sys.stderr)
        errs += 1
    render_calls = len(re.findall(r"(?m)^\s+lang_selector\.render\(\)\s*$", text))
    if render_calls != 1:
        print(f"ERROR: lang_selector.render() calls={render_calls} (want 1)", file=sys.stderr)
        errs += 1
    if 'elem_classes=["sidebar-btn"], visible=False)' not in text:
        print("ERROR: sidebar buttons not hidden", file=sys.stderr)
        errs += 1
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
