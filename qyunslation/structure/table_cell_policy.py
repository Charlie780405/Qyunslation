# SPDX-License-Identifier: MPL-2.0
"""PLAN-035a：表格单元格 translation_policy 与数字 token 审计 SSOT。"""
from __future__ import annotations

import re
from collections import Counter

from .models import TranslationPolicy
from .protect import protect_tokens

_PRESERVE_CELL = re.compile(
    r"^(?:"
    # 括号内只允许数值/符号：「46.1 (18.3)」是数据，「3 (Moderate)」「12 (SD 3.4)」含文字，必须翻译
    r"[-+±]?\d+(?:\.\d+)?(?:%|(?:\s*\([\d\s.,;:%–—\-+±/≥≤<>=]*\))?)?"
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
    # 「n = 30」与「n\u2009=\u200930」、「（12）」与「(12)」、「m2」与「m²」是同一数字
    norm = (text or "").translate(_FULLWIDTH_PARENS).translate(_SUPERSCRIPT_DIGITS)
    return [re.sub(r"\s+", "", tok) for tok in _DIGIT_TOKEN.findall(norm)]


_SUPERSCRIPT_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
# 面积/体积单位的角标：kg/m2 → kg/m²。只认小写长度单位，避免误伤 M2 巨噬细胞、IL-2 等。
_UNIT_EXPONENT = re.compile(r"(?<![A-Za-z0-9])((?:[kcmμµ]?m))([23])(?![A-Za-z0-9.\-])")
_EXPONENT_SUP = {"2": "²", "3": "³"}


def restore_unit_superscripts(text: str) -> str:
    """文本层把角标压平成普通数字（m2）；单位后的 2/3 还原为 ² ³。"""
    return _UNIT_EXPONENT.sub(lambda m: m.group(1) + _EXPONENT_SUP[m.group(2)], text or "")


_CELL_PUNCT = str.maketrans(
    {"（": "(", "）": ")", "％": "%", "＝": "=", "＋": "+", "＜": "<", "＞": ">", "−": "-"}
    | {0xFF10 + i: ord("0") + i for i in range(10)}
    | {0xFF21 + i: ord("A") + i for i in range(26)}
    | {0xFF41 + i: ord("a") + i for i in range(26)}
)
_NEQ_PAREN = re.compile(r"\(\s*([nN])\s*=\s*(\d+)\s*\)")
# 组名与 (n=30) 之间必须有空格：原文表头就是两行（Placebo group / (n = 32)），空格是排版器唯一的换行点
_CJK_BEFORE_NEQ = re.compile(r"(?<=[\u4e00-\u9fff])[ \u2009]*(?=\([nN]=\d+\))")


def compact_table_punctuation(text: str) -> str:
    """文献表单元格的标点紧凑化（窄列不折行、括号不撑宽）。

    - 全角括号/百分号/等号/全角字母数字 → 半角（Noto 全角括号两侧留白，`（ n = 30 ）` 偏宽）
    - `(n = 30)` → `(n=30)`
    - 汉字与 `(n=…)` 之间恰好一个空格：`总计(n=93)` → `总计 (n=93)`，窄列在此处换行，不在括号内折断
    只动这些符号，不碰 `，。：；？！` 等中文标点；数字比对本就忽略空白，不受影响。
    """
    out = (text or "").translate(_CELL_PUNCT)
    out = _NEQ_PAREN.sub(lambda m: f"({m.group(1)}={m.group(2)})", out)
    return _CJK_BEFORE_NEQ.sub(" ", out)


_FULLWIDTH_PARENS = str.maketrans({"（": "(", "）": ")", "％": "%", "＝": "="})


def digit_tokens_preserved(source: str, translated: str) -> bool:
    return Counter(extract_digit_tokens(source)) == Counter(extract_digit_tokens(translated))


def assert_digit_tokens_preserved(source: str, translated: str, *, block_id: str = "") -> None:
    if digit_tokens_preserved(source, translated):
        return
    suffix = f":{block_id}" if block_id else ""
    raise ValueError(f"TABLE_DIGIT_DRIFT{suffix}")
