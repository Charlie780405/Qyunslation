# SPDX-License-Identifier: MPL-2.0
"""PLAN-034e：源文规范化与占位符/数字签名。"""
from __future__ import annotations

import re

# 对齐 structure/protect 思路：用类型标签构成签名，不依赖 BabelDOC。
_SIG_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("URL", re.compile(r"https?://\S+", re.I)),
    ("DOI", re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)),
    ("REG", re.compile(r"\b(?:CTR|NCT|CHICTR|EUCTR|ISRCTN)[-:]?[A-Z0-9-]{4,}\b", re.I)),
    ("DATE", re.compile(r"\b\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\b")),
    ("PCT", re.compile(r"\b\d+(?:\.\d+)?%")),
    ("NUM", re.compile(r"\b\d+(?:\.\d+)?(?:\s*(?:mg|kg|ml|mm|cm|µg|ng|IU))?\b", re.I)),
    ("CITE", re.compile(r"\[\d+(?:[-,]\d+)*\]")),
    ("PH", re.compile(r"\{\{[^}]+\}\}|⟦[^⟧]+⟧|%\([a-zA-Z0-9_]+\)s|\{[a-zA-Z0-9_]+\}")),
)


def normalize_source(text: str) -> str:
    """空白折叠 + casefold。"""
    return " ".join((text or "").casefold().split())


def placeholder_signature(text: str) -> str:
    """按出现顺序收集数字/占位符类型标签，形如 ``NUM|PCT|URL``。"""
    if not text:
        return ""
    hits: list[tuple[int, int, str]] = []
    for name, pattern in _SIG_PATTERNS:
        for m in pattern.finditer(text):
            hits.append((m.start(), m.end(), name))
    if not hits:
        return ""
    hits.sort(key=lambda x: (x[0], x[1]))
    # 去重叠：保留先出现、更长优先已由排序保证；跳过被覆盖区间
    labels: list[str] = []
    cursor = -1
    for start, end, name in hits:
        if start < cursor:
            continue
        labels.append(name)
        cursor = end
    return "|".join(labels)
