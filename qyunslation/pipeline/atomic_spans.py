# SPDX-License-Identifier: MPL-2.0
"""PLAN-071c：原子 span 保护——译前遮蔽、译后还原。"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Longer patterns first where alternatives overlap.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "email",
        re.compile(
            r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
            r"(?![A-Za-z0-9._%+-])"
        ),
    ),
    (
        "url",
        re.compile(
            r"(?i)\b(?:https?://|www\.)[^\s<>\"']+"
        ),
    ),
    (
        "reference_id",
        re.compile(r"\bReference\s+ID\s*[:：]?\s*\d+\b", re.I),
    ),
    (
        "pind",
        re.compile(r"\bPIND\s*[:：]?\s*\d+\b", re.I),
    ),
    (
        "ind",
        re.compile(r"\bIND\s*[:：]?\s*\d+\b", re.I),
    ),
    (
        "regulatory_cite",
        re.compile(r"\b(?:21\s*CFR|ICH\s+[A-Z]\d+(?:\([A-Z]\))?)\b", re.I),
    ),
    (
        "ordinal",
        re.compile(r"\b(\d+)(st|nd|rd|th)\b", re.I),
    ),
)

_TOKEN_RE = re.compile(r"⟦QYSPAN:([a-z_]+):(\d+)⟧")


@dataclass(frozen=True)
class AtomicSpan:
    kind: str
    index: int
    text: str
    token: str


@dataclass
class ShieldResult:
    text: str
    spans: list[AtomicSpan]

    def restore(self, translated: str) -> str:
        return restore_atomic_spans(translated, self.spans)


def shield_atomic_spans(text: str) -> ShieldResult:
    """Replace protected spans with opaque tokens."""
    if not text:
        return ShieldResult(text=text, spans=[])
    spans: list[AtomicSpan] = []
    out = text
    for kind, pattern in _PATTERNS:
        # Collect matches on current out, replace from end to keep offsets stable.
        matches = list(pattern.finditer(out))
        if not matches:
            continue
        pieces: list[str] = []
        last = 0
        for match in matches:
            pieces.append(out[last : match.start()])
            index = len(spans)
            token = f"⟦QYSPAN:{kind}:{index}⟧"
            spans.append(
                AtomicSpan(kind=kind, index=index, text=match.group(0), token=token)
            )
            pieces.append(token)
            last = match.end()
        pieces.append(out[last:])
        out = "".join(pieces)
    return ShieldResult(text=out, spans=spans)


def restore_atomic_spans(text: str, spans: list[AtomicSpan]) -> str:
    if not text or not spans:
        return text
    by_token = {span.token: span.text for span in spans}

    def _sub(match: re.Match[str]) -> str:
        token = match.group(0)
        return by_token.get(token, token)

    restored = _TOKEN_RE.sub(_sub, text)
    # Defense: strip LaTeX-ish ordinal artifacts if any leaked.
    restored = re.sub(r"\^\{?(st|nd|rd|th)\}?", "", restored, flags=re.I)
    return restored


def strip_ordinal_artifacts(text: str) -> str:
    """Standalone cleaner compatible with letter_layout.clean_text intent."""
    text = re.sub(r"\^\{?(st|nd|rd|th)\}?", "", text, flags=re.I)
    return text
