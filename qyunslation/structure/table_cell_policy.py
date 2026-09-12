# SPDX-License-Identifier: MPL-2.0
"""PLAN-035a：表格单元格 translation_policy 与数字 token 审计 SSOT。"""
from __future__ import annotations

import re
from collections import Counter

from .models import TranslationPolicy
from .protect import protect_tokens

_PRESERVE_CELL = re.compile(
    r"^(?:"
    r"[-+±]?\d+(?:\.\d+)?(?:%|(?:\s*\([^)]*\))?)?"
    r"|n\s*=\s*\d+"
    r"|\(\d+(?:[.,]\d+)?%?\)"
    r"|\d+/\d+"
    r"|N/?A"
    r"|[\d\s.,%+\-±×/°℃℉μmgkKMLlNnHhPpAaVvWwΩ]+"
    r")$",
    re.I,
)

_DOSE_ABBR = re.compile(r"^Q\d+W$", re.I)

_UNIT_ONLY = re.compile(
    r"^(?:mg|mL|ml|kg|g|µg|ug|ng|μg|mm|cm|m|w|h|d|wk|weeks?|days?|hrs?|"
    r"IU|U|%|ppm|nM|µM|uM|mM|M|pg|ng/mL|mg/kg)$",
    re.I,
)

_DIGIT_TOKEN = re.compile(
    r"(?:"
    r"n\s*=\s*\d+"
    r"|\(\d+(?:[.,]\d+)?%?\)"
    r"|\d+(?:\.\d+)?%"
    r"|\d+(?:\.\d+)?"
    r")",
    re.I,
)


def is_numeric_or_unit(text: str) -> bool:
    """图内 OCR / 文档块：纯数字、单位或 preserve 单元格，不送翻译。"""
    if is_preserve_cell(text):
        return True
    s = (text or "").strip()
    if _UNIT_ONLY.fullmatch(s):
        return True
    return bool(
        re.match(
            r"^[\d\.\,\s]+(?:mg|mL|ml|kg|g|µg|ug|ng|mm|cm|%|w|h|d)$",
            s,
            re.I,
        )
    )


def is_preserve_cell(text: str) -> bool:
    """纯数值/占位单元格：不送 LLM，原样透传。"""
    t = (text or "").strip()
    if not t:
        return True
    return bool(_PRESERVE_CELL.fullmatch(t))


def classify_cell_policy(text: str) -> TranslationPolicy:
    t = (text or "").strip()
    if not t or is_preserve_cell(t) or _DOSE_ABBR.fullmatch(t):
        return TranslationPolicy.PRESERVE
    _protected, mapping = protect_tokens(t)
    if mapping:
        return TranslationPolicy.PROTECT_TOKENS
    return TranslationPolicy.TRANSLATE


def extract_digit_tokens(text: str) -> list[str]:
    return _DIGIT_TOKEN.findall(text or "")


def digit_tokens_preserved(source: str, translated: str) -> bool:
    return Counter(extract_digit_tokens(source)) == Counter(extract_digit_tokens(translated))


def assert_digit_tokens_preserved(source: str, translated: str, *, block_id: str = "") -> None:
    if digit_tokens_preserved(source, translated):
        return
    suffix = f":{block_id}" if block_id else ""
    raise ValueError(f"TABLE_DIGIT_DRIFT{suffix}")
