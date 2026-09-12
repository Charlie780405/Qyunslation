#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""PLAN-047c：pdf_creater 丢段前用 unicode 兜底落笔，禁止静默删字。"""
from __future__ import annotations

import sys
from pathlib import Path

SITE = Path.home() / ".local/share/uv/tools/pdf2zh-next/lib/python3.12/site-packages"
PC = SITE / "babeldoc/format/pdf/document_il/backend/pdf_creater.py"
MARKER = "_QY_047C_NO_DROP"

OLD = """        if not chars and paragraph.unicode and paragraph.debug_id:
            logger.error(
                f"Unable to export paragraphs that have "
                f"not yet been formatted: {paragraph}",
            )
            return chars
        return chars
"""

NEW = r'''        if not chars and paragraph.unicode and paragraph.debug_id:
            # _QY_047C_NO_DROP: unicode 兜底落笔，允许溢出；仅兜底失败才丢弃
            try:
                from babeldoc.format.pdf.document_il.il_version_1 import (
                    Box,
                    PdfCharacter,
                )
                text = paragraph.unicode or ""
                style = paragraph.pdf_style
                box = paragraph.box
                if text and style is not None and box is not None:
                    x0 = float(box.x)
                    y2 = float(box.y2)
                    fs = float(getattr(style, "font_size", 8.0) or 8.0)
                    baseline = y2 - fs * 0.85
                    cursor = x0
                    scale = float(getattr(paragraph, "optimal_scale", None) or 1.0)
                    for ch in text:
                        if ch in ("\n", "\r"):
                            continue
                        w = fs if ("\u4e00" <= ch <= "\u9fff") else fs * 0.5
                        char = PdfCharacter(
                            pdf_character_id=None,
                            char_unicode=ch,
                            box=Box(x=cursor, y=baseline, x2=cursor + w, y2=baseline + fs),
                            pdf_style=style,
                            scale=scale,
                            vertical=False,
                            advance=w,
                            xobj_id=getattr(paragraph, "xobj_id", None),
                        )
                        chars.append(char)
                        cursor += w
                    if chars:
                        logger.warning(
                            "_QY_047C_NO_DROP: fallback-rendered %d chars debug_id=%s",
                            len(chars),
                            paragraph.debug_id,
                        )
                        return chars
            except Exception as _qy_exc:
                logger.error(
                    "_QY_047C_NO_DROP: fallback failed: %s; dropping paragraph",
                    _qy_exc,
                )
                return chars
            logger.error(
                f"Unable to export paragraphs that have "
                f"not yet been formatted: {paragraph}",
            )
            return chars
        return chars
'''


def main() -> int:
    if not PC.is_file():
        print(f"missing {PC}", file=sys.stderr)
        return 1
    text = PC.read_text(encoding="utf-8")
    if MARKER in text:
        print(f"already patched: {PC}")
        return 0
    if OLD not in text:
        print("target block not found; pdf_creater.py shape changed", file=sys.stderr)
        return 1
    PC.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print(f"patched {PC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
