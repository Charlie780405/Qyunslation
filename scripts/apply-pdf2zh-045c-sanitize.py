#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-045c：BabelDOC post_translate 写出前剥离 IL span/id 乱码。"""
from __future__ import annotations

import sys
from pathlib import Path

SITE = Path.home() / ".local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages"
IL = SITE / "babeldoc/format/pdf/document_il/midend/il_translator.py"
MARKER = "_QY_045C_SANITIZE"


HELPER = f'''
def {MARKER}(text):
    try:
        from qyunslation.structure.text_sanitize import sanitize_translated_text
        cleaned, _codes = sanitize_translated_text(text)
        return cleaned
    except Exception:
        return text
'''

OLD_POST = """    def post_translate_paragraph(
        self,
        paragraph: PdfParagraph,
        tracker: ParagraphTranslateTracker,
        translate_input,
        translated_text: str,
    ):
        \"\"\"Post-translation processing: update paragraph with translated text.\"\"\"
        tracker.set_output(translated_text)
"""

NEW_POST = f"""    def post_translate_paragraph(
        self,
        paragraph: PdfParagraph,
        tracker: ParagraphTranslateTracker,
        translate_input,
        translated_text: str,
    ):
        \"\"\"Post-translation processing: update paragraph with translated text.\"\"\"
        translated_text = {MARKER}(translated_text)  # PLAN-045c
        tracker.set_output(translated_text)
"""


def patch(text: str) -> tuple[str, bool]:
    changed = False
    if HELPER.strip() not in text:
        anchor = "logger = logging.getLogger(__name__)"
        if anchor not in text:
            print("ERROR: logger anchor missing", file=sys.stderr)
            return text, False
        text = text.replace(anchor, anchor + "\n" + HELPER, 1)
        changed = True
    if "PLAN-045c" not in text and OLD_POST in text:
        text = text.replace(OLD_POST, NEW_POST, 1)
        changed = True
    elif f"{MARKER}(translated_text)" in text:
        pass
    elif "PLAN-045c" not in text:
        print("ERROR: post_translate_paragraph anchor missing", file=sys.stderr)
        return text, False
    return text, changed


def main() -> int:
    if not IL.is_file():
        print(f"ERROR: missing {IL}", file=sys.stderr)
        return 1
    raw = IL.read_text(encoding="utf-8")
    patched, changed = patch(raw)
    if changed:
        IL.write_text(patched, encoding="utf-8")
        print(f"patched {IL}")
    else:
        print(f"unchanged {IL}")
    if MARKER not in patched or "PLAN-045c" not in patched:
        print("ERROR: 045c sanitize not present after patch", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
