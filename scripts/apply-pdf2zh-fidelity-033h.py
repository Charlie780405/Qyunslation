#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-033h：BabelDOC 消费参考文献 PRESERVE，并按字体名补字重。"""
from __future__ import annotations

import sys
from pathlib import Path

SITE = Path(
    "/home/dev/.local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages"
)
IL = SITE / "babeldoc/format/pdf/document_il/midend/il_translator_llm_only.py"
TERMS = SITE / "babeldoc/format/pdf/document_il/midend/automatic_term_extractor.py"
CREATER = SITE / "babeldoc/format/pdf/document_il/frontend/il_creater.py"
FONTMAP = SITE / "babeldoc/format/pdf/document_il/utils/fontmap.py"
MARKER = "_QY_033H_PRESERVE"


HOOK_SHOULD = f"""
        if {MARKER}(paragraph.unicode):
            return False
"""

HELPER = f'''
def {MARKER}(text):
    try:
        from qyunslation.structure.babeldoc_policy import paragraph_is_preserved
        return paragraph_is_preserved(text)
    except Exception:
        return False
'''

RESET = """
        try:
            from qyunslation.structure.babeldoc_policy import reset_preserve_gate
            reset_preserve_gate()
        except Exception:
            pass
"""


def _once(text: str, needle: str, insert: str) -> tuple[str, bool]:
    if insert in text:
        return text, False
    if needle not in text:
        return text, False
    return text.replace(needle, needle + insert, 1), True


def patch_il(text: str) -> tuple[str, bool]:
    changed = False
    if HELPER.strip() not in text:
        anchor = "logger = logging.getLogger(__name__)"
        if anchor in text:
            text = text.replace(anchor, anchor + "\n" + HELPER, 1)
            changed = True
    text, ok = _once(
        text,
        "        if require_body_text and not self._is_body_text_paragraph(paragraph):\n            return False\n",
        HOOK_SHOULD,
    )
    changed = changed or ok
    if "reset_preserve_gate" not in text:
        text, ok = _once(text, "    def translate(self, docs: Document) -> None:\n", RESET)
        changed = changed or ok
    old_title = """                if paragraph.layout_label == "title":
                    logger.info(f"Found title paragraph: {paragraph.unicode}")
                    return paragraph"""
    new_title = """                if paragraph.layout_label == "title":
                    try:
                        from qyunslation.structure.babeldoc_policy import title_is_usable_context
                        if not title_is_usable_context(paragraph.unicode):
                            continue
                    except Exception:
                        pass
                    logger.info(f"Found title paragraph: {paragraph.unicode}")
                    return paragraph"""
    if old_title in text and "title_is_usable_context" not in text:
        text = text.replace(old_title, new_title, 1)
        changed = True
    process_page_after = """            if _pdf2zh_skip_already_target_lang(
                paragraph.unicode,
                self.translation_config.lang_in,
                self.translation_config.lang_out,
            ):
                if pbar:
                    pbar.advance(1)
                translated_ids.add(id(paragraph))
                continue
"""
    process_page_hook = """            if _QY_033H_PRESERVE(paragraph.unicode):
                if pbar:
                    pbar.advance(1)
                translated_ids.add(id(paragraph))
                continue
"""
    text, ok = _once(text, process_page_after, process_page_hook)
    changed = changed or ok
    return text, changed


def patch_terms(text: str) -> tuple[str, bool]:
    insert = """            try:
                from qyunslation.structure.babeldoc_policy import paragraph_is_preserved
                if paragraph_is_preserved(paragraph.unicode):  # _QY_033H_PRESERVE
                    continue
            except Exception:
                pass
"""
    after_plain = """        for paragraph in page.pdf_paragraph:
            if paragraph.debug_id is None or paragraph.unicode is None:
                continue
"""
    after_pbar = """        for paragraph in page.pdf_paragraph:
            if paragraph.debug_id is None or paragraph.unicode is None:
                pbar.advance(1)
                continue
"""
    if "paragraph_is_preserved" in text:
        return text, False
    if after_pbar in text:
        insert_pbar = """            try:
                from qyunslation.structure.babeldoc_policy import paragraph_is_preserved
                if paragraph_is_preserved(paragraph.unicode):  # _QY_033H_PRESERVE
                    pbar.advance(1)
                    continue
            except Exception:
                pass
"""
        return text.replace(after_pbar, after_pbar + insert_pbar, 1), True
    if after_plain in text:
        return text.replace(after_plain, after_plain + insert, 1), True
    return text, False


def patch_creater(text: str) -> tuple[str, bool]:
    old = """            bold = mupdf_font.is_bold
            italic = mupdf_font.is_italic
"""
    new = """            from qyunslation.structure.font_style import infer_bold, infer_italic
            bold = bool(mupdf_font.is_bold) or infer_bold(font_name)
            italic = bool(mupdf_font.is_italic) or infer_italic(font_name)
"""
    if "infer_bold(font_name)" in text:
        return text, False
    if old not in text:
        return text, False
    return text.replace(old, new, 1), True


def patch_fontmap(text: str) -> tuple[str, bool]:
    old = """        elif isinstance(original_font, PdfFont):
            bold = original_font.bold
            italic = original_font.italic
            monospaced = original_font.monospace
            serif = original_font.serif
"""
    new = """        elif isinstance(original_font, PdfFont):
            from qyunslation.structure.font_style import infer_bold, infer_italic
            name = getattr(original_font, "name", None) or getattr(original_font, "font_id", "")
            bold = bool(original_font.bold) or infer_bold(name)
            italic = bool(original_font.italic) or infer_italic(name)
            monospaced = original_font.monospace
            serif = original_font.serif
"""
    if "infer_bold(name)" in text:
        return text, False
    if old not in text:
        return text, False
    return text.replace(old, new, 1), True


def apply_file(path: Path, patcher) -> bool:
    if not path.is_file():
        print(f"SKIP missing {path}", file=sys.stderr)
        return False
    text = path.read_text(encoding="utf-8")
    new, changed = patcher(text)
    if changed:
        path.write_text(new, encoding="utf-8")
        print(f"patched {path}")
    else:
        print(f"unchanged {path}")
    return changed


def main() -> int:
    apply_file(IL, patch_il)
    apply_file(TERMS, patch_terms)
    apply_file(CREATER, patch_creater)
    apply_file(FONTMAP, patch_fontmap)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
