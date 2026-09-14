# SPDX-License-Identifier: MPL-2.0
"""PLAN-033h：参考文献整区 PRESERVE，标题也不译。

只认独立标题行，不认正文里的 see [12] / as shown in References。
Appendix/Supplement 之后恢复翻译。
"""
from __future__ import annotations

import re

# A stable ASCII sentinel is deliberately used instead of translated text. It
# survives markdown/XML conversion and can be checked before we put the exact
# source section back into the result.
_REFERENCE_SENTINEL_RE = re.compile(r"__QYUNSLATION_REFERENCE_([0-9A-F]{8})__")

HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(references|bibliography|参考文献|参考资料)\s*[:：]?\s*\.?\s*$",
    re.IGNORECASE,
)
SECTION_BREAK_RE = re.compile(
    r"^\s*(appendix|supplementary|acknowledg(?:e)?ments|致谢|附录)\b",
    re.IGNORECASE,
)
ENTRY_RE = re.compile(
    r"^\s*(?:"
    r"\[\d+\]\s*\S+"  # [12] Author / [12]Author
    r"|\d+\.\s+\S+"  # 12. Author
    r"|\d{1,3}\s+[A-ZÀ-ÖØ-Þ]"  # 12 Author
    r"|\d{1,3}(?=[A-Z][A-Za-zÀ-ÖØ-öø-ÿ\-']{1,})"  # 1Langanan 粘连
    r")"
)


def first_line(text: str) -> str:
    return (text or "").strip().splitlines()[0].strip() if text and text.strip() else ""


def is_reference_heading(text: str) -> bool:
    line = first_line(text)
    return bool(line) and bool(HEADING_RE.match(line))


def is_section_break(text: str) -> bool:
    line = first_line(text)
    return bool(line) and bool(SECTION_BREAK_RE.match(line)) and not is_reference_heading(text)


def is_reference_entry(text: str) -> bool:
    """条目以 [12] / 12. / 12 Author / 1Langanan 开头。正文 see [12] 不会命中。"""
    blob = (text or "").lstrip()
    if not blob:
        return False
    # 正文内联引用：字母… see [12] …
    if re.match(r"^[A-Za-z\u4e00-\u9fff]", blob) and re.search(
        r"\b(?:see|as shown in|cf\.?)\s*\[\d+\]", blob, re.I
    ):
        return False
    return bool(ENTRY_RE.match(blob))


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
    """给术语采集用：丢掉整个参考文献区（标题+条目）。"""
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
            if kind in {"heading", "entry"}:
                continue
            if is_section_break(text):
                in_refs = False
            parts.append(text)
        heading_y = None
    return "\n".join(parts)


def _markdown_heading_level(line: str) -> int | None:
    match = re.match(r"^\s*(#{1,6})\s+\S", line or "")
    return len(match.group(1)) if match else None


def mask_reference_sections(text: str) -> tuple[str, dict[str, str]]:
    """Replace complete markdown reference sections with opaque sentinels.

    The section heading is included in the protected range. A section ends at
    the next markdown heading of the same or a higher level; when the input is
    a reference-only chunk it therefore safely runs to EOF. The returned map is
    intentionally explicit so callers can fail closed if a model drops a
    sentinel instead of accidentally returning partially translated citations.
    """
    source = str(text or "")
    if not source:
        return source, {}
    lines = source.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if is_reference_heading(line)]
    if not starts:
        return source, {}

    ranges: list[tuple[int, int]] = []
    for start in starts:
        level = _markdown_heading_level(lines[start])
        end = len(lines)
        if level is not None:
            for index in range(start + 1, len(lines)):
                next_level = _markdown_heading_level(lines[index])
                if next_level is not None and next_level <= level:
                    end = index
                    break
        ranges.append((start, end))

    # Overlapping headings are possible in malformed OCR. Merge them so no
    # reference line can leak into the translation request.
    merged: list[tuple[int, int]] = []
    for start, end in ranges:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    masked: list[str] = []
    sections: dict[str, str] = {}
    cursor = 0
    for ordinal, (start, end) in enumerate(merged, start=1):
        masked.extend(lines[cursor:start])
        section = "".join(lines[start:end])
        token = f"__QYUNSLATION_REFERENCE_{ordinal:08X}__"
        sections[token] = section
        # Keep a line boundary where the protected section was, avoiding a
        # sentinel being glued to the preceding paragraph after conversion.
        masked.append(token + ("" if section.endswith(("\n", "\r")) else "\n"))
        cursor = end
    masked.extend(lines[cursor:])
    return "".join(masked), sections


class ReferenceProtectionError(ValueError):
    """The model modified or removed a protected reference sentinel."""


def restore_reference_sections(
    text: str,
    sections: dict[str, str],
    *,
    strict: bool = False,
) -> str:
    """Restore exact source sections; optionally fail if any sentinel is gone."""
    result = str(text or "")
    if not sections:
        return result
    missing = [token for token in sections if token not in result]
    if missing and strict:
        raise ReferenceProtectionError(
            "REFERENCE_SENTINEL_MISSING:" + ",".join(sorted(missing))
        )
    for token, section in sections.items():
        result = result.replace(token, section)
    return result
