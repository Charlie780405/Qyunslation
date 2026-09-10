# SPDX-License-Identifier: MPL-2.0
"""PLAN-033j：数字、单位、缩写、引用、DOI、URL 占位保护。"""
from __future__ import annotations

import re
from collections import Counter

_PATTERNS = (
    ("EMAIL", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("URL", re.compile(r"https?://\S+", re.I)),
    ("DOI", re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)),
    ("REG", re.compile(r"\b(?:CTR|NCT|CHICTR|EUCTR|ISRCTN)[-:]?[A-Z0-9-]{4,}\b", re.I)),
    (
        "PROTOCOL",
        re.compile(
            r"\b(?=[A-Z0-9-]{6,}\b)(?=[A-Z0-9-]*\d)(?=[A-Z0-9-]*-)"
            r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b",
            re.I,
        ),
    ),
    ("DATE", re.compile(r"\b\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\b")),
    ("PHONE", re.compile(r"(?<!\w)(?:\+?\d[\d()\s-]{6,}\d)(?!\w)")),
    ("PCT", re.compile(r"\b\d+(?:\.\d+)?%")),
    ("NUM", re.compile(r"\b\d+(?:\.\d+)?(?:\s*(?:mg|kg|ml|mm|cm|µg|ng|IU|vs))\b", re.I)),
    ("CITE", re.compile(r"\[\d+(?:[-,]\d+)*\]")),
    ("ABBR", re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)?\b")),
)


def protect_tokens(text: str) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}
    out = text
    index = 0
    for name, pattern in _PATTERNS:
        def repl(match: re.Match[str], *, _name=name) -> str:
            nonlocal index
            index += 1
            key = f"⟦{_name}{index}⟧"
            mapping[key] = match.group(0)
            return key

        out = pattern.sub(repl, out)
    return out, mapping


def restore_tokens(text: str, mapping: dict[str, str]) -> str:
    out = text
    for key, value in mapping.items():
        out = out.replace(key, value)
    return out


def missing_protected_tokens(source: str, translated: str) -> list[str]:
    """Return immutable source tokens that disappeared from translated text."""
    _protected, mapping = protect_tokens(source)
    required = Counter(mapping.values())
    return [
        token
        for token, count in required.items()
        if (translated or "").count(token) < count
    ]
