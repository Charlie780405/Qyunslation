#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-007：ocr_workaround 时恢复 page.base_operations，保留扫描底图。

BabelDOC pdf_creater.update_page_content_stream 默认注释掉了底图绘制；
扫描件 + ocr_workaround 需要：底图 → 白底矩形 → 译文，否则 mono 只剩白底稀疏字。
"""
from __future__ import annotations

import sys
from pathlib import Path

CREATER = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/"
    "babeldoc/format/pdf/document_il/backend/pdf_creater.py"
)

MARKER = "_qy_ocr_base_ops"

OLD = """        page_op = BitStream()
        # q {ops_base}Q 1 0 0 1 {x0} {y0} cm {ops_new}
        # page_op.append(b"q ")
        # base_op = page.base_operations.value
        # base_op = zstd_decompress(base_op)
        # page_op.append(base_op.encode())
        # page_op.append(b" \\n")
        page_op.append(ctm_for_ops)
        page_op.append(b" \\n")
"""

# NOTE: the file uses real newlines after \\n in bytes literals — match exact source
OLD_EXACT = (
    "        page_op = BitStream()\n"
    "        # q {ops_base}Q 1 0 0 1 {x0} {y0} cm {ops_new}\n"
    '        # page_op.append(b"q ")\n'
    "        # base_op = page.base_operations.value\n"
    "        # base_op = zstd_decompress(base_op)\n"
    "        # page_op.append(base_op.encode())\n"
    '        # page_op.append(b" \\n")\n'
    "        page_op.append(ctm_for_ops)\n"
    '        page_op.append(b" \\n")\n'
)

NEW = (
    "        page_op = BitStream()\n"
    f"        # {MARKER}: restore scanned page background under ocr_workaround\n"
    "        # q {ops_base}Q 1 0 0 1 {x0} {y0} cm {ops_new}\n"
    "        if translation_config.ocr_workaround and page.base_operations:\n"
    '            page_op.append(b"q ")\n'
    "            base_op = page.base_operations.value\n"
    "            base_op = zstd_decompress(base_op)\n"
    "            page_op.append(base_op.encode())\n"
    '            page_op.append(b" Q\\n")\n'
    "        page_op.append(ctm_for_ops)\n"
    '        page_op.append(b" \\n")\n'
)


def apply(text: str) -> str:
    if MARKER in text:
        print("already patched:", CREATER)
        return text
    if OLD_EXACT not in text:
        # try without escaped space before \\n variants
        alt_old = OLD_EXACT.replace('b" \\n"', 'b" \\n"')
        if "page_op.append(ctm_for_ops)" not in text:
            print("ERROR: anchor not found", file=sys.stderr)
            return text
        # more resilient: replace the commented block region
        start = text.find("        page_op = BitStream()\n")
        if start < 0:
            print("ERROR: BitStream anchor not found", file=sys.stderr)
            return text
        end = text.find("        # Create render context\n", start)
        if end < 0:
            print("ERROR: render context anchor not found", file=sys.stderr)
            return text
        text = text[:start] + NEW + "\n" + text[end:]
        print("patched (resilient):", CREATER)
        return text
    text = text.replace(OLD_EXACT, NEW, 1)
    print("patched:", CREATER)
    return text


GUI = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/pdf2zh_next/gui.py"
)
GUI_MARKER = "_qy_mono_fallback_dual"
GUI_OLD = '''            result_entry = {
                "original_name": filename,
                "original_path": str(file_path),
                "mono": str(mono_path) if mono_path and mono_path.exists() else None,
                "dual": str(dual_path) if dual_path and dual_path.exists() else None,
'''
GUI_NEW = '''            # PLAN-007: ocr_workaround 偶发 Mono PDF: None → 用 dual 兜底下载
            _mono = str(mono_path) if mono_path and mono_path.exists() else None
            _dual = str(dual_path) if dual_path and dual_path.exists() else None
            if _mono is None and _dual is not None:
                _mono = _dual  # ''' + GUI_MARKER + '''
            result_entry = {
                "original_name": filename,
                "original_path": str(file_path),
                "mono": _mono,
                "dual": _dual,
'''


def apply_gui(text: str) -> str:
    if GUI_MARKER in text:
        print("already patched gui mono-fallback:", GUI)
        return text
    if GUI_OLD not in text:
        print("WARNING: gui mono fallback anchor not found", file=sys.stderr)
        return text
    text = text.replace(GUI_OLD, GUI_NEW, 1)
    print("patched gui mono-fallback:", GUI)
    return text


def main() -> int:
    if not CREATER.is_file():
        print(f"ERROR: {CREATER}", file=sys.stderr)
        return 1
    original = CREATER.read_text(encoding="utf-8")
    updated = apply(original)
    if updated != original:
        CREATER.write_text(updated, encoding="utf-8")
    if MARKER not in updated:
        print("ERROR: patch not applied", file=sys.stderr)
        return 1

    if GUI.is_file():
        g0 = GUI.read_text(encoding="utf-8")
        g1 = apply_gui(g0)
        if g1 != g0:
            GUI.write_text(g1, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
