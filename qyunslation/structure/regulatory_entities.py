# SPDX-License-Identifier: MPL-2.0
"""PLAN-042e：监管表单受控实体与确定性映射。"""
from __future__ import annotations

import re

from qyunslation.glossary.governance import build_merged_dict, normalize_source

_CJK = re.compile(r"[\u4e00-\u9fff]")
# 仅整格期次标签（避免长标题被整段替换成 Phase II）
_ROMAN_PHASE_FULL = re.compile(
    r"^(?P<roman>[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩIVXivx]+)\s*期$"
)
_ARABIC_MISREAD_FULL = re.compile(r"^(?:11|111)\s*期$")
# 长文内嵌期次：就地改写，不吞整句
_ROMAN_PHASE_EMBED = re.compile(
    r"(?P<roman>[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]|(?<![A-Za-z])II(?![A-Za-z])|(?<![A-Za-z])III?(?![A-Za-z])|(?<![A-Za-z])IV(?![A-Za-z]))\s*期"
)

_ROMAN_TO_PHASE = {
    "i": "Phase I",
    "ii": "Phase II",
    "iii": "Phase III",
    "iv": "Phase IV",
    "ⅰ": "Phase I",
    "ⅱ": "Phase II",
    "ⅲ": "Phase III",
    "ⅳ": "Phase IV",
}


def lookup_controlled(source: str, *, mapping: dict[str, str] | None = None) -> str | None:
    """精确命中受控词表则返回 target，否则 None。"""
    text = (source or "").strip()
    if not text:
        return None
    table = mapping if mapping is not None else build_merged_dict()
    if text in table:
        return table[text]
    key = normalize_source(text)
    for src, tgt in table.items():
        if normalize_source(src) == key:
            return tgt
    return None


def translate_or_preserve(source: str, *, mapping: dict[str, str] | None = None) -> str:
    """受控命中则译；含机构/人名特征且未命中则保留原文（禁自由生成）。"""
    hit = lookup_controlled(source, mapping=mapping)
    if hit is not None:
        return hit
    if _looks_entity(source):
        return source
    return source


def _looks_entity(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if any(tok in t for tok in ("医院", "大学", "学院", "药业", "生物", "有限公司", "股份")):
        return True
    if _CJK.fullmatch(t) and 2 <= len(t) <= 4:
        return True
    return False


def _roman_to_phase(roman: str) -> str | None:
    ascii_roman = (
        roman.casefold()
        .replace("ⅰ", "i")
        .replace("ⅱ", "ii")
        .replace("ⅲ", "iii")
        .replace("ⅳ", "iv")
    )
    return _ROMAN_TO_PHASE.get(ascii_roman)


def normalize_phase_label(text: str) -> str:
    """仅整格期次：II 期 / 11 期 → Phase N。长标题原样返回。"""
    raw = (text or "").strip()
    if not raw:
        return raw
    m = _ROMAN_PHASE_FULL.match(raw)
    if m:
        phase = _roman_to_phase(m.group("roman"))
        if phase:
            return phase
    if _ARABIC_MISREAD_FULL.match(raw):
        return "Phase II"
    hit = lookup_controlled(raw)
    if hit is not None and hit.startswith("Phase "):
        return hit
    return raw


def rewrite_embedded_phase(text: str) -> str:
    """长文内把 II 期 / Ⅱ 期 就地换成 Phase II，保留其余内容。"""
    raw = text or ""

    def repl(match: re.Match[str]) -> str:
        phase = _roman_to_phase(match.group("roman"))
        return phase or match.group(0)

    return _ROMAN_PHASE_EMBED.sub(repl, raw)


def map_section_heading(text: str, *, mapping: dict[str, str] | None = None) -> str | None:
    return lookup_controlled(text, mapping=mapping)
