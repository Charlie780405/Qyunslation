# SPDX-License-Identifier: MPL-2.0
"""PLAN-033j：数字、单位、缩写、引用、DOI、URL 占位保护。"""
from __future__ import annotations

import re

_PATTERNS = (
    ("URL", re.compile(r"https?://\S+", re.I)),
    ("DOI", re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)),
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
