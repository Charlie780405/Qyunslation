#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-018：高级选项下移到翻译按钮下方 + flex-wrap 根因修复。

须在 apply-pdf2zh-layout-polish.py 之后执行。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/"
    "site-packages/pdf2zh_next/gui.py"
)

CSS_MARKER = "/* _qy_adv_options_css */"

CSS_BLOCK = """
    /* _qy_adv_options_css */
    .qy-col-left {
        flex-wrap: nowrap !important;
    }
    .qy-adv-acc {
        margin-top: 10px !important;
        flex: 0 0 auto !important;
        min-height: 0 !important;
        max-width: 100% !important;
    }
    .qy-adv-acc > :last-child {
        max-height: min(44vh, 400px) !important;
        overflow-y: auto !important;
    }
    .qy-col-left {
        padding-bottom: 8px !important;
    }
"""


def _left_span(text: str) -> tuple[int, int] | None:
    left = text.find('elem_classes=["qy-col-left"]')
    mid = text.find('elem_classes=["qy-col-mid"]')
    if left < 0 or mid < 0 or mid <= left:
        return None
    return left, mid


def _find_accordion_block(text: str, start: int, end: int) -> tuple[int, int] | None:
    """Return [start, end) of `with gr.Accordion("高级选项"...):` block in range."""
    marker = 'elem_classes=["qy-adv-acc"]'
    mi = text.find(marker, start, end)
    if mi < 0:
        return None
    head = text.rfind("with gr.Accordion(", start, mi)
    if head < 0:
        return None
    # Indent of the `with` line
    line_start = text.rfind("\n", start, head) + 1
    indent = head - line_start
    # Body lines are more indented; stop at first line with indent <= accordion indent
    # after the `):` that opens the with-block
    open_paren = text.find("):", mi, end)
    if open_paren < 0:
        return None
    pos = open_paren + 2
    if pos < end and text[pos] == "\n":
        pos += 1
    while pos < end:
        # next line
        nl = text.find("\n", pos, end)
        if nl < 0:
            nl = end
        line = text[pos:nl]
        if line.strip() == "":
            # include trailing blank only if more body follows; stop after body
            # peek next non-empty
            peek = nl + 1
            while peek < end and text[peek] in " \t":
                # stay
                next_nl = text.find("\n", peek, end)
                if next_nl < 0:
                    break
                if text[peek:next_nl].strip() == "":
                    peek = next_nl + 1
                    continue
                break
            next_nl = text.find("\n", peek, end)
            if next_nl < 0:
                next_nl = end
            next_line = text[peek:next_nl]
            if next_line.strip() == "" or (len(next_line) - len(next_line.lstrip(" ")) <= indent and next_line.strip()):
                # end before this blank (or at blank if end of body)
                return line_start, pos  # exclude trailing blanks
            pos = nl + 1
            continue
        line_indent = len(line) - len(line.lstrip(" "))
        if line.strip() and line_indent <= indent:
            return line_start, pos
        pos = nl + 1
    return line_start, pos


def _find_action_row_end(text: str, start: int, end: int) -> int | None:
    """Return index just after cancel_btn Button closing paren of action-row."""
    row = text.find('with gr.Row(elem_classes=["action-row"])', start, end)
    if row < 0:
        return None
    cancel = text.find("cancel_btn = gr.Button(", row, end)
    if cancel < 0:
        return None
    # Find matching closing paren of Button(
    i = text.find("(", cancel)
    depth = 0
    for j in range(i, end):
        ch = text[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                # include trailing newline if present
                k = j + 1
                if k < end and text[k] == "\n":
                    k += 1
                return k
    return None


def apply_move_accordion(text: str) -> tuple[str, bool]:
    span = _left_span(text)
    if not span:
        print("WARNING: left/mid span missing", file=sys.stderr)
        return text, False
    left, mid = span
    left_body = text[left:mid]

    action_i = left_body.find('with gr.Row(elem_classes=["action-row"])')
    acc_i = left_body.find('elem_classes=["qy-adv-acc"]')
    if action_i >= 0 and acc_i > action_i:
        return text, False

    block_span = _find_accordion_block(text, left, mid)
    if not block_span:
        print("WARNING: qy-adv-acc accordion missing in left column", file=sys.stderr)
        return text, False
    b0, b1 = block_span
    block = text[b0:b1].rstrip("\n") + "\n"

    text_wo = text[:b0] + text[b1:]
    span2 = _left_span(text_wo)
    if not span2:
        return text, False
    left2, mid2 = span2
    insert_at = _find_action_row_end(text_wo, left2, mid2)
    if insert_at is None:
        print("WARNING: action-row end not found for accordion insert", file=sys.stderr)
        return text, False
    text2 = text_wo[:insert_at] + "\n" + block + text_wo[insert_at:]
    return text2, True


SAVE_BTN_CANON = '''                                save_btn = gr.Button(
                                    _("Save Settings"),
                                    variant="secondary",
                                    elem_classes=["save-settings-btn"],
                                    visible=False,
                                )
'''


def apply_hide_save_btn(text: str) -> tuple[str, bool]:
    span = _left_span(text)
    if not span:
        return text, False
    left, mid = span
    idx = text.find("save_btn = gr.Button(", left, mid)
    if idx < 0:
        print("WARNING: save_btn not found in left column", file=sys.stderr)
        return text, False
    # Expand to full statement start (line start)
    line_start = text.rfind("\n", left, idx) + 1
    paren = text.find("(", idx)
    depth = 0
    end = None
    for j in range(paren, mid):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    if end is None:
        return text, False
    if end < mid and text[end] == "\n":
        end += 1
    current = text[line_start:end]
    if current == SAVE_BTN_CANON:
        return text, False
    return text[:line_start] + SAVE_BTN_CANON + text[end:], True


def _custom_css_span(text: str) -> tuple[int, int] | None:
    """Return [content_start, close_quote_index) for custom_css triple-quoted string."""
    start = text.find('custom_css = """')
    if start < 0:
        return None
    content_start = start + len('custom_css = """')
    m = re.search(r"\n[ \t]*\"\"\"", text[content_start:])
    if not m:
        return None
    return content_start, content_start + m.start()


def _strip_adv_css_blocks(text: str) -> tuple[str, int]:
    """Remove every _qy_adv_options_css block (may be misplaced)."""
    pat = re.compile(
        r"\n[ \t]*/\* _qy_adv_options_css \*/\n"
        r"(?:[ \t]*[^\n]+\n)*?"
        r"[ \t]*\.qy-col-left \{\n"
        r"[ \t]*padding-bottom:[^\n]+\n"
        r"[ \t]*\}\n",
        re.S,
    )
    return pat.subn("\n", text)


def apply_css(text: str) -> tuple[str, bool]:
    desired = "\n" + CSS_BLOCK.rstrip() + "\n"
    span = _custom_css_span(text)
    if not span:
        print("WARNING: custom_css span missing", file=sys.stderr)
        return text, False
    c0, c1 = span
    css_body = text[c0:c1]
    polish_i = css_body.find("/* _qy_layout_polish_css */")
    adv_i = css_body.find(CSS_MARKER)
    if (
        polish_i >= 0
        and adv_i > polish_i
        and text.count(CSS_MARKER) == 1
        and desired.strip() in css_body
    ):
        return text, False

    text2, _n = _strip_adv_css_blocks(text)
    text = text2
    span = _custom_css_span(text)
    if not span:
        print("WARNING: custom_css span missing after strip", file=sys.stderr)
        return text, True
    c0, c1 = span
    css_body = text[c0:c1]
    if "/* _qy_layout_polish_css */" not in css_body:
        print("WARNING: polish css missing inside custom_css", file=sys.stderr)
        return text, True
    new_body = css_body.rstrip() + desired
    return text[:c0] + new_body + text[c1:], True


def apply(text: str) -> tuple[str, bool]:
    changed = False
    for fn in (apply_move_accordion, apply_hide_save_btn, apply_css):
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
        body = text[left:mid]
        action_i = body.find('with gr.Row(elem_classes=["action-row"])')
        acc_i = body.find('elem_classes=["qy-adv-acc"]')
        need(action_i >= 0, "action-row missing in left")
        need(acc_i > action_i, "accordion must be after action-row")
        need(body.count('elem_classes=["qy-adv-acc"]') == 1, "qy-adv-acc not unique in left")
        sb = body.find("save_btn = gr.Button")
        need(sb >= 0 and "visible=False" in body[sb : sb + 400], "save_btn visible=False missing")
    span = _custom_css_span(text)
    need(span is not None, "custom_css span missing")
    if span:
        css_body = text[span[0] : span[1]]
        need(CSS_MARKER in css_body, "adv options css not inside custom_css")
        polish_i = css_body.find("/* _qy_layout_polish_css */")
        adv_i = css_body.find(CSS_MARKER)
        need(polish_i >= 0 and adv_i > polish_i, "adv css must follow polish css")
        need("flex-wrap: nowrap" in css_body[adv_i : adv_i + 800], "nowrap rule missing")
    need(text.count(CSS_MARKER) == 1, "adv css marker count != 1")

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
