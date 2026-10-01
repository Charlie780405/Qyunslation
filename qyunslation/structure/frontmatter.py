# SPDX-License-Identifier: MPL-2.0
"""Conservative PDF front-matter classification for literature and posters."""
from __future__ import annotations

import re
from dataclasses import dataclass

AUTHOR = "author"
AFFILIATION = "affiliation"
BODY = "body"

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_ORCID = re.compile(r"\bORCID\b|\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b", re.I)
_CORRESPONDING = re.compile(r"\b(?:corresponding|presenting)\s+author\b", re.I)
_DEGREE = re.compile(
    r"\b(?:MD|M\.D\.|PhD|Ph\.D\.|PharmD|MPH|MSc|MS|MA|MBA|BS|BA|RN|FRCP|FACP)\b",
    re.I,
)
_NAME = re.compile(r"\b[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’-]{1,}\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’-]{1,}\b")
_AFFILIATION = re.compile(
    r"\b(?:university|college|school of|department of|division of|faculty of|"
    r"hospital|medical cent(?:er|re)|institute|institution|clinic|laborator(?:y|ies)|"
    r"research cent(?:er|re)|foundation|academy)\b",
    re.I,
)
_BODY_SENTENCE = re.compile(
    r"\b(?:patient|patients|study|treatment|evaluated|received|reported|showed|"
    r"demonstrated|was|were|is|are|has|have|after|before|during)\b",
    re.I,
)


@dataclass(frozen=True, slots=True)
class FrontmatterClassification:
    role: str
    preserve: bool
    review_required: bool
    confidence: float
    reason: str


def classify_frontmatter_text(text: str | None) -> FrontmatterClassification:
    """Classify only high-signal standalone author and affiliation paragraphs.

    The detector deliberately prefers a false-negative over preserving a prose
    sentence.  A separate layout-aware caller may promote uncertain first-page
    lines to manual review without sending them to the translator.
    """
    value = " ".join((text or "").split()).strip()
    if not value:
        return FrontmatterClassification(BODY, False, False, 0.0, "empty")
    affiliation = bool(_AFFILIATION.search(value))
    if affiliation:
        return FrontmatterClassification(
            AFFILIATION, False, True, 0.95, "organization/address markers"
        )
    names = _NAME.findall(value)
    degree = bool(_DEGREE.search(value))
    prose = bool(_BODY_SENTENCE.search(value))
    explicit_author = bool(
        _CORRESPONDING.search(value)
        or _ORCID.search(value)
        or (_EMAIL.search(value) and (names or "author" in value.casefold()))
    )
    author_shape = explicit_author or (len(names) >= 2 and degree) or (
        len(names) == 1 and degree and not prose and len(value.split()) <= 18
    )
    if author_shape:
        reason = "explicit author marker" if explicit_author else "names and credentials"
        return FrontmatterClassification(AUTHOR, True, False, 0.95, reason)
    return FrontmatterClassification(BODY, False, False, 0.0, "no front-matter signal")


def paragraph_role(text: str | None) -> str:
    return classify_frontmatter_text(text).role


def paragraph_is_author(text: str | None) -> bool:
    return classify_frontmatter_text(text).role == AUTHOR
