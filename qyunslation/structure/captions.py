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


_NO_SPACE_BEFORE = set(".,;:)]}%/")
_NO_SPACE_AFTER = set("([{\"'")


def _needs_word_space(prev: str, nxt: str) -> bool:
    """ScienceDirect 把 'Table 2' 与 'Response' 分成两个 span，中间没有空格字形。"""
    if not prev or not nxt:
        return False
    if prev[-1].isspace() or nxt[0].isspace():
        return False
    if nxt[0] in _NO_SPACE_BEFORE or prev[-1] in _NO_SPACE_AFTER:
        return False
    # 1,234 / well-known / 3.14 —— 但 'Table 2.' + 'Response' 仍要空格
    if prev[-1] == "," or prev[-1] == "-":
        return False
    if prev[-1] == "." and nxt[0].isdigit():
        return False
    return True


def join_span_texts(parts: list[str]) -> str:
    """按阅读顺序拼接 span；缺词界时补一个空格。幂等。"""
    out: list[str] = []
    for raw in parts:
        text = raw or ""
        if not text:
            continue
        if out and _needs_word_space(out[-1], text):
            out.append(" ")
        out.append(text)
    return "".join(out)


def block_plain_text(block: dict) -> str:
    """一个 text block 的可读文本。行与 span 都走 join_span_texts。"""
    lines: list[str] = []
    for line in block.get("lines", []) or []:
        spans = [span.get("text", "") for span in line.get("spans", []) or []]
        joined = join_span_texts(spans)
        if joined:
            lines.append(joined)
    return join_span_texts(lines).strip()


def continued_table_anchors(page) -> list[tuple[int, float, tuple]]:
    """跨页续表题注 [(table_num, y0, bbox)]，不含主表题注。"""
    rows: list[tuple[int, float, tuple]] = []
    try:
        blocks = page.get_text("dict").get("blocks", [])
    except Exception:
        return []
    for b in blocks:
        if b.get("type") != 0:
            continue
        text = block_plain_text(b)
        if not text or is_toc_line(text) or not is_continued_caption(text):
            continue
        num = table_caption_num(text)
        if not num:
            continue
        bb = tuple(b.get("bbox") or (0, 0, 0, 0))
        rows.append((num, float(bb[1]), bb))
    return sorted(rows, key=lambda x: (x[1], x[2][0]))


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
        text = block_plain_text(b)
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
