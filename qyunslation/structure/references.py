# SPDX-License-Identifier: MPL-2.0
"""PLAN-033d：参考文献标题可译、条目保留。

只认独立标题行，不认正文里的 see [12] / as shown in References。
"""
from __future__ import annotations

import re

HEADING_RE = re.compile(
    r"^\s*(references|bibliography|参考文献|参考资料)\s*\.?\s*$",
    re.IGNORECASE,
)
SECTION_BREAK_RE = re.compile(
    r"^\s*(appendix|supplementary|acknowledg(?:e)?ments|致谢|附录)\b",
    re.IGNORECASE,
)
ENTRY_RE = re.compile(r"^\s*(?:\[\d+\]|\d+\.)\s+\S+")


def first_line(text: str) -> str:
    return (text or "").strip().splitlines()[0].strip() if text and text.strip() else ""


def is_reference_heading(text: str) -> bool:
    line = first_line(text)
    return bool(line) and bool(HEADING_RE.match(line))


def is_section_break(text: str) -> bool:
    line = first_line(text)
    return bool(line) and bool(SECTION_BREAK_RE.match(line)) and not is_reference_heading(text)


def is_reference_entry(text: str) -> bool:
    """条目以 [12] / 12. 开头。正文 see [12] for details 不会命中。"""
    return bool(ENTRY_RE.match((text or "").lstrip()))


def heading_y_from_blocks(raw_blocks: list) -> float | None:
    for raw in raw_blocks or []:
        if len(raw) < 5:
            continue
        if is_reference_heading(str(raw[4])):
            return float(raw[1])
    return None


def classify_body(
    text: str,
    y0: float,
    *,
    in_references: bool,
    heading_y: float | None,
) -> str:
    """返回 heading / entry / body。"""
    if is_reference_heading(text):
        return "heading"
    if is_section_break(text):
        return "body"
    if not in_references:
        return "body"
    if heading_y is not None and y0 < heading_y:
        return "body"
    return "entry"


def text_excluding_reference_entries(doc) -> str:
    """给术语采集用：丢掉参考文献条目，保留标题和正文。"""
    parts: list[str] = []
    in_refs = False
    for page in doc:
        try:
            raw_blocks = page.get_text("blocks") or []
        except Exception:
            continue
        heading_y = heading_y_from_blocks(raw_blocks)
        if heading_y is not None:
            in_refs = True
        for raw in raw_blocks:
            if len(raw) < 5:
                continue
            text = str(raw[4])
            y0 = float(raw[1])
            kind = classify_body(
                text, y0, in_references=in_refs, heading_y=heading_y
            )
            if kind == "heading":
                parts.append(text)
                continue
            if kind == "entry":
                continue
            if is_section_break(text):
                in_refs = False
            parts.append(text)
        heading_y = None
    return "\n".join(parts)
