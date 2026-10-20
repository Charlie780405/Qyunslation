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


# ---- 下角标/上角标（PLAN-083d）-------------------------------------------------------------------
# 文本层把 C_max、AUC_0-τ、t_1/2z 压平成 Cmax、AUC0-τ、t1/2z。落笔时按「基名 + 角标」还原：
# 角标用小字号、偏移基线；不改文本内容（数字比对、翻译缓存不受影响）。
# 角标对优先取自原文表的真实 span（字号明显更小、基线偏移），再并上下面的内置 PK/统计常用写法。
_DASH = "-\u2010\u2011\u2012\u2013\u2014\u2212"
_DEFAULT_SCRIPT_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("C", "max", "sub"), ("C", "min", "sub"), ("C", "trough", "sub"), ("C", "ss", "sub"), ("C", "avg", "sub"),
    ("T", "max", "sub"), ("T", "min", "sub"), ("t", "max", "sub"),
    ("t", "1/2z", "sub"), ("t", "1/2", "sub"), ("V", "z", "sub"), ("V", "ss", "sub"),
    ("AUC", "0-t", "sub"), ("AUC", "0-τ", "sub"), ("AUC", "0-∞", "sub"), ("AUC", "0-last", "sub"),
    ("AUC", "inf", "sub"), ("AUC", "last", "sub"), ("AUC", "tau", "sub"), ("AUC", "τ", "sub"),
    ("MRT", "inf", "sub"), ("MRT", "0-t", "sub"), ("MRT", "last", "sub"),
    ("R", "ac_Cmax", "sub"), ("R", "ac_AUCtau", "sub"), ("R", "ac_AUC", "sub"), ("R", "ac", "sub"),
)
_script_pairs: list[tuple[str, str, str]] = []
_script_re: re.Pattern[str] | None = None
_script_kinds: dict[tuple[str, str], str] = {}


def _escape_sub(sub: str) -> str:
    return "".join(f"[{_DASH}]" if ch in _DASH else re.escape(ch) for ch in sub)


def set_script_pairs(pairs=None) -> None:
    """文献表落笔前设置角标对 (基名, 角标, "sub"|"sup")，内置 PK 常用写法一并启用。

    None = 关闭（监管路径等不还原角标）；[] = 只用内置对。
    """
    global _script_pairs, _script_re, _script_kinds
    merged: dict[tuple[str, str], str] = {}
    if pairs is None:
        _script_kinds, _script_pairs, _script_re = {}, [], None
        return
    for base, sub, kind in list(_DEFAULT_SCRIPT_PAIRS) + list(pairs):
        base, sub = str(base or "").strip(), str(sub or "").strip()
        if base and sub and kind in {"sub", "sup"}:
            merged[(base, sub.translate(str.maketrans({c: "-" for c in _DASH})))] = kind
    _script_kinds = merged
    _script_pairs = [(b, s, k) for (b, s), k in merged.items()]
    if not merged:
        _script_re = None
        return
    ordered = sorted(merged, key=lambda p: -(len(p[0]) + len(p[1])))
    body = "|".join(f"(?:{re.escape(b)})(?:{_escape_sub(s)})" for b, s in ordered)
    _script_re = re.compile(rf"(?<![A-Za-z0-9µμ])(?:{body})(?![A-Za-z0-9])")


set_script_pairs(None)


def split_script_runs(text: str) -> list[tuple[str, str]]:
    """[(片段, ""|"sub"|"sup")]：基名保持正常，角标部分单独成段。"""
    text = text or ""
    if _script_re is None or not text:
        return [(text, "")]
    out: list[tuple[str, str]] = []
    cursor = 0
    for match in _script_re.finditer(text):
        raw = match.group(0)
        pair = next(
            (
                (base, raw[len(base):], kind)
                for (base, sub), kind in _script_kinds.items()
                if raw.startswith(base) and raw[len(base):].translate(str.maketrans({c: "-" for c in _DASH})) == sub
            ),
            None,
        )
        if pair is None:
            continue
        base, sub_text, kind = pair
        if match.start() > cursor:
            out.append((text[cursor : match.start()], ""))
        out.append((base, ""))
        out.append((sub_text, kind))
        cursor = match.end()
    if cursor < len(text):
        out.append((text[cursor:], ""))
    return [(chunk, kind) for chunk, kind in out if chunk] or [(text, "")]


def has_script_runs(text: str) -> bool:
    return any(kind for _chunk, kind in split_script_runs(text))


_MARKER_RE = re.compile(r"[A-Za-z*†‡§]{1,2}")


def strip_footnote_markers(text: str, pairs) -> tuple[str, list[tuple[str, str]]]:
    """把原文里压平的脚注上标（150 mga → 150 mg + 上标 a）拿掉再翻译，避免模型把 mga 当成 mg/kg 之类。

    只处理来自原文真实上标 span 的 (基名, 标记, "sup")；返回 (去标记后的文本, [(基名, 标记)])。
    """
    removed: list[tuple[str, str]] = []
    out = text or ""
    for base, sub, kind in pairs or []:
        if kind != "sup" or not _MARKER_RE.fullmatch(sub or ""):
            continue
        pattern = re.compile(rf"(?<![A-Za-z0-9])({re.escape(base)}){re.escape(sub)}(?![A-Za-z0-9])")
        if pattern.search(out):
            out = pattern.sub(lambda m: m.group(1), out, count=1)
            removed.append((base, sub))
    return out, removed


def restore_footnote_markers(text: str, removed: list[tuple[str, str]]) -> str:
    """译文里基名之后接回脚注标记（落笔时按上标画）；找不到基名就不加。"""
    out = text or ""
    for base, sub in removed:
        out = re.sub(
            rf"(?<![A-Za-z0-9])({re.escape(base)})(?![A-Za-z])", lambda m: m.group(1) + sub, out, count=1
        )
    return out
