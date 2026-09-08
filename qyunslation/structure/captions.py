# SPDX-License-Identifier: MPL-2.0
"""PLAN-030c：题注检测（从 Hermes lit_tables 内联，无跨仓 import）。"""
from __future__ import annotations

import re

_SP = r"[^\S\n]"
_ROMAN = r"([IVXLC]+|\d+)"
_WILEY_WORD = re.compile(
    r"(?:[A-Z]{1,2}[\s\u00ad\u2009\u2002\xa0]+){2,}[A-Z]{1,2}"
)
_ROMAN_VAL = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
    "VIII": 8,
    "IX": 9,
    "X": 10,
    "XI": 11,
    "XII": 12,
    "XIII": 13,
    "XIV": 14,
    "XV": 15,
}
CAPTION_LINE = re.compile(
    rf"^{_SP}*(?:[Tt]able|TABLE|表){_SP}*{_ROMAN}"
    rf"(?:{_SP}*[.．:：、|]{_SP}*|{_SP}+(?=[A-Z\u4e00-\u9fff])|{_SP}*$)",
    re.M,
)
ROMAN_CAPTION = re.compile(
    rf"^{_SP}*(?:[Tt]able|TABLE|表){_SP}*([IVX]{{1,6}}){_SP}*[.．:：、]",
    re.M,
)
FIGURE_LINE = re.compile(
    rf"^{_SP}*(?:[Ff]igure|FIGURE|[Ff]ig\.|FIG|图){_SP}*(\d+)"
    rf"(?:{_SP}*[.．:：、|]{_SP}*|{_SP}+(?=[A-Z\u4e00-\u9fff])|{_SP}*$)",
    re.M,
)
TOC_LINE = re.compile(r"\.{4,}|…{2,}|\s\.\s\.\s\.")


def squeeze_caps(s: str) -> str:
    return _WILEY_WORD.sub(
        lambda m: re.sub(r"[\s\u00ad\u2009\u2002\xa0]+", "", m.group(0)), s or ""
    )


def _cap_num(m) -> int:
    if not m:
        return 0
    g = m.group(1)
    return int(g) if g.isdigit() else _ROMAN_VAL.get(g.upper(), 0)


def table_caption_num(text: str) -> int | None:
    t = squeeze_caps(text)
    m = CAPTION_LINE.match(t)
    if m:
        g = m.group(1)
        return int(g) if g.isdigit() else _ROMAN_VAL.get(g.upper())
    m = ROMAN_CAPTION.match(t)
    if m:
        return _ROMAN_VAL.get(m.group(1).upper())
    return None


def figure_caption_num(text: str) -> int | None:
    t = squeeze_caps(text)
    m = FIGURE_LINE.match(t)
    return _cap_num(m) if m else None


def is_toc_line(line: str) -> bool:
    return bool(TOC_LINE.search(line or ""))


def is_continued_caption(s: str) -> bool:
    t = (s or "").strip()
    if not t:
        return False
    if re.search(r"(?i)\bcontinued\b", t):
        return True
    return bool(re.match(r"(?i)^\(?continues\)?\.?$", t))


def caption_anchors(page) -> list[tuple[str, int, float, tuple]]:
    """同页 Table/Figure 题注 [(kind, num, y0, bbox)]，按 y 再 x 排。"""
    rows: list[tuple[str, int, float, tuple]] = []
    try:
        blocks = page.get_text("dict").get("blocks", [])
    except Exception:
        return []
    for b in blocks:
        if b.get("type") != 0:
            continue
        text = "".join(
            s.get("text", "")
            for ln in b.get("lines", [])
            for s in ln.get("spans", [])
        ).strip()
        if not text:
            continue
        bb = tuple(b.get("bbox") or (0, 0, 0, 0))
        y0 = float(bb[1])
        tn = table_caption_num(text)
        fn = figure_caption_num(text)
        if tn and not is_toc_line(text) and not is_continued_caption(text):
            rows.append(("table", tn, y0, bb))
        elif fn and not is_toc_line(text):
            rows.append(("figure", fn, y0, bb))
    return sorted(rows, key=lambda x: (x[2], x[3][0]))
