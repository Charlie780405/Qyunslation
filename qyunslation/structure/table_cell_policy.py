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

_DIGIT_TOKEN = re.compile(
    r"(?:"
    r"n\s*=\s*\d+"
    r"|\(\d+(?:[.,]\d+)?%?\)"
    r"|\d+(?:\.\d+)?%"
    r"|\d+(?:\.\d+)?"
    r")",
    re.I,
)


def is_preserve_cell(text: str) -> bool:
    """纯数值/占位单元格：不送 LLM，原样透传。"""
    t = (text or "").strip()
    if not t:
        return True
    return bool(_PRESERVE_CELL.fullmatch(t))


def classify_cell_policy(text: str) -> TranslationPolicy:
    t = (text or "").strip()
    if not t or is_preserve_cell(t):
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
