# SPDX-License-Identifier: MPL-2.0
"""PLAN-042e：监管表单受控实体与确定性映射。"""
from __future__ import annotations

import re

from qyunslation.glossary.governance import build_merged_dict, normalize_source

_CJK = re.compile(r"[\u4e00-\u9fff]")
_ROMAN_PHASE = re.compile(
    r"(?P<roman>[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩIVXivx]+)\s*期"
)
_ARABIC_MISREAD = re.compile(r"(?<!\d)(?P<digits>11|111)\s*期")

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
    # 2–4 汉字且无标点：疑似人名
    if _CJK.fullmatch(t) and 2 <= len(t) <= 4:
        return True
    return False


def normalize_phase_label(text: str) -> str:
    """纠正 II 期被抽成 11 期等；罗马数字期次 → Phase N。"""
    raw = (text or "").strip()
    if not raw:
        return raw
    m = _ROMAN_PHASE.search(raw)
    if m:
        roman = m.group("roman").casefold()
        # 全角罗马
        for k, v in _ROMAN_TO_PHASE.items():
            if roman == k or roman.replace("ⅰ", "i").replace("ⅱ", "ii").replace("ⅲ", "iii") == k:
                return v
        ascii_roman = (
            roman.replace("ⅰ", "i")
            .replace("ⅱ", "ii")
            .replace("ⅲ", "iii")
            .replace("ⅳ", "iv")
        )
        if ascii_roman in _ROMAN_TO_PHASE:
            return _ROMAN_TO_PHASE[ascii_roman]
    # 常见误读：II → 11（两个竖线被识别为十一）
    if _ARABIC_MISREAD.fullmatch(raw) or re.fullmatch(r"11\s*期", raw):
        return "Phase II"
    hit = lookup_controlled(raw)
    return hit if hit is not None else raw


def map_section_heading(text: str, *, mapping: dict[str, str] | None = None) -> str | None:
    return lookup_controlled(text, mapping=mapping)
