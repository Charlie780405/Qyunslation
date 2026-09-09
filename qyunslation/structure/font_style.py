# SPDX-License-Identifier: MPL-2.0
"""PLAN-033h：字重/斜体推断。PDF flags 不足时看字体名。"""
from __future__ import annotations

import re

_BOLD_NAME = re.compile(
    r"(bold|semibold|semi[-_ ]?bold|black|heavy|extrabold|ultra|\.b(?:old)?\b)",
    re.IGNORECASE,
)
_BLACK_NAME = re.compile(r"(black|heavy)", re.IGNORECASE)
_SEMIBOLD_NAME = re.compile(r"semi", re.IGNORECASE)
_ITALIC_NAME = re.compile(r"(italic|oblique|\.i\b)", re.IGNORECASE)
_DOT_B = re.compile(r"(?:^|[.\-_])B(?:old)?(?:$|[.\-_])")


def infer_font_weight(font_name: str | None, *, flags_bold: bool | None = None) -> str:
    name = font_name or ""
    if _BLACK_NAME.search(name):
        return "black"
    if _SEMIBOLD_NAME.search(name) and _BOLD_NAME.search(name):
        return "semibold"
    if _BOLD_NAME.search(name) or _DOT_B.search(name):
        return "bold"
    if flags_bold:
        return "bold"
    return "regular"


def infer_bold(font_name: str | None, *, flags_bold: bool | None = None) -> bool:
    return infer_font_weight(font_name, flags_bold=flags_bold) != "regular"


def infer_italic(font_name: str | None, *, flags_italic: bool | None = None) -> bool:
    if _ITALIC_NAME.search(font_name or ""):
        return True
    return bool(flags_italic)


def cap_body_gap(source_gap_pt: float, font_size: float) -> float:
    """普通正文段距：跟源文，但截掉异常巨大空白。"""
    size = max(float(font_size or 10.0), 1.0)
    gap = max(float(source_gap_pt), 0.0)
    ceiling = size * 1.8
    if gap > size * 4.0:
        return ceiling
    return min(gap, ceiling)
