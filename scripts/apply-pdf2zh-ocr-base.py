#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""扫描件译文页：整页白底盖英文栅格，再画中文。

007 曾恢复 page.base_operations 留 Logo；底图是英文扫描件，
段落白底盖不全就会中英叠字。008 起改为不铺底图 + 整页白底。
不改泰州 HPD。
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

RESTORE_OLD = (
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

NEW = (
    "        page_op = BitStream()\n"
    f"        # {MARKER}: do not restore scanned raster (English would show through)\n"
    "        page_op.append(ctm_for_ops)\n"
    '        page_op.append(b" \\n")\n'
)


def apply(text: str) -> str:
    if "do not restore scanned raster" in text:
        print("already patched (no-raster):", CREATER)
        return text
    if RESTORE_OLD in text:
        text = text.replace(RESTORE_OLD, NEW, 1)
        print("patched (disable raster restore):", CREATER)
        return text
    if MARKER in text and "restore scanned page background" in text:
        # 旧注释+if 块，按行替换
        text = text.replace(
            "        # _qy_ocr_base_ops: restore scanned page background under ocr_workaround\n"
            "        # q {ops_base}Q 1 0 0 1 {x0} {y0} cm {ops_new}\n"
            "        if translation_config.ocr_workaround and page.base_operations:\n"
            '            page_op.append(b"q ")\n'
            "            base_op = page.base_operations.value\n"
            "            base_op = zstd_decompress(base_op)\n"
            "            page_op.append(base_op.encode())\n"
            '            page_op.append(b" Q\\n")\n',
            f"        # {MARKER}: do not restore scanned raster (English would show through)\n",
            1,
        )
        print("patched (strip restore if):", CREATER)
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


FINDER = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/"
    "babeldoc/format/pdf/document_il/midend/paragraph_finder.py"
)
COVER_MARKER = "_qy_ocr_fullpage_white"
COVER_ANCHOR = """    def add_text_fill_background(self, page: Page):
        layout_map = {layout.id: layout for layout in page.page_layout}
"""
COVER_NEW = """    def add_text_fill_background(self, page: Page):
        # """ + COVER_MARKER + """: 整页白底盖扫描英文，段落缝不再漏字
        _box = None
        if page.cropbox and page.cropbox.box:
            _box = page.cropbox.box
        elif page.mediabox and page.mediabox.box:
            _box = page.mediabox.box
        if _box is not None:
            page.pdf_rectangle.append(
                PdfRectangle(
                    box=Box(_box.x, _box.y, _box.x2, _box.y2),
                    fill_background=True,
                    graphic_state=WHITE,
                    debug_info=False,
                    xobj_id=-1,
                )
            )
        layout_map = {layout.id: layout for layout in page.page_layout}
"""


TC = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/"
    "babeldoc/format/pdf/translation_config.py"
)
SKIP_FORMS_MARKER = "_qy_ocr_skip_forms"
AUTO_CLR_OLD = """        if auto_enable_ocr_workaround:
            self.ocr_workaround = False
            self.skip_scanned_detection = False
"""
AUTO_CLR_NEW = """        if auto_enable_ocr_workaround and not ocr_workaround:
            self.ocr_workaround = False
            self.skip_scanned_detection = False
"""

SKIP_FORMS_OLD = """        if self.ocr_workaround:
            self.remove_non_formula_lines = False
"""
SKIP_FORMS_NEW = """        if self.ocr_workaround:
            self.remove_non_formula_lines = False
            self.skip_form_render = True  # """ + SKIP_FORMS_MARKER + """
"""


FORM_SKIP_OLD = """        if not translation_config.skip_form_render:
            all_forms = list(page.pdf_form) + formula_forms
"""
FORM_SKIP_NEW = """        if not translation_config.skip_form_render and not translation_config.ocr_workaround:
            all_forms = list(page.pdf_form) + formula_forms
"""

MODEL = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages/"
    "pdf2zh_next/config/model.py"
)
KEEP_OCR_OLD = """        if self.pdf.auto_enable_ocr_workaround and self.pdf.ocr_workaround:
            self.pdf.ocr_workaround = False
            log.warning(
                "The system detection results will override the manually set OCR workaround."
            )
"""
KEEP_OCR_NEW = """        if self.pdf.auto_enable_ocr_workaround and self.pdf.ocr_workaround:
            pass  # _qy_keep_manual_ocr: 手动 ocr_workaround 不被 auto 清掉
"""


def apply_form_skip_render(text: str) -> str:
    if "not translation_config.ocr_workaround" in text and "skip_form_render" in text:
        print("already patched form-skip-on-ocr:", CREATER)
        return text
    if FORM_SKIP_OLD not in text:
        print("WARNING: form render anchor not found", file=sys.stderr)
        return text
    text = text.replace(FORM_SKIP_OLD, FORM_SKIP_NEW, 1)
    print("patched form-skip-on-ocr:", CREATER)
    return text


def apply_keep_manual_ocr(text: str) -> str:
    if "_qy_keep_manual_ocr" in text:
        print("already patched keep manual ocr:", MODEL)
        return text
    if KEEP_OCR_OLD not in text:
        print("WARNING: auto_enable ocr override anchor not found", file=sys.stderr)
        return text
    text = text.replace(KEEP_OCR_OLD, KEEP_OCR_NEW, 1)
    print("patched keep manual ocr:", MODEL)
    return text


def apply_skip_forms(text: str) -> str:
    if AUTO_CLR_OLD in text:
        text = text.replace(AUTO_CLR_OLD, AUTO_CLR_NEW, 1)
        print("patched auto_enable 不再清手动 ocr_workaround:", TC)
    if SKIP_FORMS_MARKER in text:
        print("already patched skip_form_render:", TC)
        return text
    if SKIP_FORMS_OLD not in text:
        print("WARNING: ocr_workaround skip_form anchor not found", file=sys.stderr)
        return text
    text = text.replace(SKIP_FORMS_OLD, SKIP_FORMS_NEW, 1)
    print("patched skip_form_render:", TC)
    return text


def apply_cover(text: str) -> str:
    if COVER_MARKER in text:
        print("already patched fullpage white:", FINDER)
        return text
    if COVER_ANCHOR not in text:
        print("WARNING: add_text_fill_background anchor not found", file=sys.stderr)
        return text
    text = text.replace(COVER_ANCHOR, COVER_NEW, 1)
    print("patched fullpage white:", FINDER)
    return text


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
    updated = apply_form_skip_render(updated)
    if updated != original:
        CREATER.write_text(updated, encoding="utf-8")
    if MARKER not in updated:
        print("ERROR: patch not applied", file=sys.stderr)
        return 1
    if "not translation_config.ocr_workaround" not in updated:
        print("ERROR: form-skip-on-ocr not applied", file=sys.stderr)
        return 1

    if MODEL.is_file():
        m0 = MODEL.read_text(encoding="utf-8")
        m1 = apply_keep_manual_ocr(m0)
        if m1 != m0:
            MODEL.write_text(m1, encoding="utf-8")
        if "_qy_keep_manual_ocr" not in m1:
            print("ERROR: keep manual ocr not applied", file=sys.stderr)
            return 1

    if TC.is_file():
        t0 = TC.read_text(encoding="utf-8")
        t1 = apply_skip_forms(t0)
        if t1 != t0:
            TC.write_text(t1, encoding="utf-8")
        if SKIP_FORMS_MARKER not in t1:
            print("ERROR: skip_form_render not applied", file=sys.stderr)
            return 1

    if FINDER.is_file():
        f0 = FINDER.read_text(encoding="utf-8")
        f1 = apply_cover(f0)
        if f1 != f0:
            FINDER.write_text(f1, encoding="utf-8")
        if COVER_MARKER not in f1:
            print("ERROR: fullpage white not applied", file=sys.stderr)
            return 1

    if GUI.is_file():
        g0 = GUI.read_text(encoding="utf-8")
        g1 = apply_gui(g0)
        if g1 != g0:
            GUI.write_text(g1, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
