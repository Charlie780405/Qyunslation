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

# PLAN-080：常见的非标准写法也认——"7. References"、"REFERENCES AND NOTES"、"Literature Cited"、
# "Works Cited"、"Reference List"。仍然只认独立标题行（整行只有这几个词）。
HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:(?:\d{1,2}|[IVX]{1,5})[.)]?\s+)?"
    r"(?:references?(?:\s+(?:cited|list|and\s+notes))?|bibliography|literature\s+cited|works\s+cited|"
    r"cited\s+(?:references|literature)|参考文献|参考资料|引用文献)"
    r"\s*[:：]?\s*\.?\s*$",
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


_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
# 期刊引文的形状：卷(期):页、年;卷:页、DOI、et al.、pp.、Vol.
_JOURNAL_RE = re.compile(
    r"\b\d{1,4}\s*\(\d{1,3}\)\s*:\s*[\w-]+"  # 153(2):345-52
    r"|[;,]\s*\d{1,4}\s*:\s*[\w-]+"  # 2024;153:345
    r"|\b\d{1,4},\s*\d{1,6}\s*[–—-]\s*\d{1,6}\s*\(\s*(?:19|20)\d{2}\s*\)"  # Nature：184, 437–449 (2021)
    r"|\bdoi\b\s*:?\s*10\.\d{4,9}/\S+|\b10\.\d{4,9}/\S+|\bdoi\b"  # "doi: 10.x/y" 只算一处
    r"|\bet\s+al\b|\bpp?\.\s*\d|\bvol\.?\s*\d",
    re.IGNORECASE,
)


# 作者列表开头："Smith, J. J." / "Scarisbrick, J. J. & Morris, S."（Nature、Vancouver 的缩写写法）
_CITED_YEAR_RE = re.compile(r"\(\s*(?:19|20)\d{2}[a-z]?\s*\)|\b(?:19|20)\d{2}[a-z]?\s*[;.:,]")
_AUTHORS_RE = re.compile(r"^\W*(?:\d{1,3}\.?\s*)?[A-Z][A-Za-z'’-]+,\s+(?:[A-Z]\.\s?){1,3}")


def is_citation_entry(text: str) -> bool:
    """不依赖"参考文献"标题也能认出的期刊引文条目：编号开头，并且有年份和期刊引文的形状。

    监管信函里的编号问题（"2. The protocol synopsis ..."）没有年份加卷期页码，不会命中；
    参考文献标题写法不标准、或标题被版面丢失时，引文仍然保留原文。
    """
    blob = " ".join((text or "").split())
    if not blob or not is_reference_entry(blob):
        return False
    if not _YEAR_RE.search(blob):
        return False
    if _JOURNAL_RE.search(blob):
        return True
    # 只有作者缩写开头时证据较弱：要求年份像引文里的年份（括号里，或后面紧跟标点），而不是句子里的 "in 2020 that"
    return bool(_AUTHORS_RE.match(blob) and _CITED_YEAR_RE.search(blob))


_CITATION_BLOCK_MIN = 2


def citation_density(text: str) -> int:
    """段落里期刊引文形状（卷:页、DOI、et al.、Nature 的"卷, 页 (年)"）出现了几处。"""
    return len(_JOURNAL_RE.findall(" ".join((text or "").split())))


def is_citation_block(text: str) -> bool:
    """段落本身就是一堆引文：不要求以编号开头，也不依赖前面有没有"参考文献"标题。

    双栏文献里，BabelDOC 的段落顺序是版面分析的顺序而不是阅读顺序，参考文献条目常被合并成
    一个从某一条中间开头的长段落，标题的位置也可能晚于条目；依赖顺序的状态机会漏掉它们。
    正文很少出现两处以上"卷:页 / DOI / et al."，所以密度可以作为不依赖顺序的判据。
    """
    blob = " ".join((text or "").split())
    return citation_density(blob) >= _CITATION_BLOCK_MIN and bool(_YEAR_RE.search(blob))


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
