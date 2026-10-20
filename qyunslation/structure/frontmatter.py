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
_PERSON_TITLE = re.compile(r"\b(?:Dr|Doctor|Prof|Professor|Mr|Mrs|Ms)\.?\b", re.I)
_SIGNATURE = re.compile(r"^(?:sincerely|respectfully|yours sincerely)[,:]?\s+", re.I)
_DEGREE = re.compile(
    r"\b(?:MD|M\.D\.|PhD|Ph\.D\.|PharmD|MPH|MSc|MS|MA|MBA|BS|BA|RN|FRCP|FACP)\b",
    re.I,
)
_NAME = re.compile(
    r"\b[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’-]{1,}(?:\s+[A-Z]\.?)?\s+"
    r"[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’-]{1,}\b"
)
_AFFILIATION = re.compile(
    r"\b(?:university|college|school of|department of|division of|faculty of|office of|"
    r"hospital|medical cent(?:er|re)|national institutes? of|institute|institution|clinic|"
    r"research cent(?:er|re)|cent(?:er|re) for|foundation|academy|organization|organisation|"
    r"food\s+(?:&|and)\s+drug\s+administration|co\.?,?\s*ltd\.?|inc\.?|llc|llp|limited|"
    r"corporation|corp\.?|gmbh)\b|"
    r"\blaborator(?:y|ies)(?=\s+(?:of|at|for)\b|[,;:]|$)",
    re.I,
)
# PLAN-080a：机构名标记（如 "Co., Ltd."、"Division of"）偶尔出现在长正文句中；
# 超过此词数的段落不按署名/机构处理，交给翻译。
_AFFILIATION_MAX_WORDS = 30
# 机构行里很少出现的功能词；正文句几乎总有。动词表（_BODY_SENTENCE）漏掉的句子靠它兜底。
_FUNCTION_WORDS = re.compile(
    r"\b(?:the|this|that|these|those|to|by|with|their|its|our|your|from|which|who|whose|but|not|"
    r"if|when|while|because|has|have|been|into|about|also|such)\b",
    re.I,
)
_LONG_LINE_WORDS = 12


def _looks_like_prose(value: str) -> bool:
    """两个以上功能词，或超过 12 个词还有一个功能词（"Office of the Director" 这类短机构行不算）。"""
    hits = len(_FUNCTION_WORDS.findall(value))
    return hits >= 2 or (hits >= 1 and len(value.split()) > _LONG_LINE_WORDS)
_BODY_SENTENCE = re.compile(
    r"\b(?:patient|patients|study|treatment|evaluated|received|reported|showed|"
    r"demonstrated|encouraged|encourages|recommend(?:ed|s)?|should|must|need(?:ed|s)?|"
    r"identify|provide|assess|refer|see|contact|submit|launch(?:es|ed)?|use(?:s|d)?|"
    r"include(?:s|d)?|conduct(?:s|ed)?|will|can|may|would|could|might|"
    r"was|were|is|are|has|have|after|before|during)\b",
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
    """Classify high-signal standalone author and affiliation paragraphs.

    The detector deliberately prefers a false-negative over preserving a prose
    sentence, since preserved front matter bypasses the translation model.
    """
    value = " ".join((text or "").split()).strip()
    if not value:
        return FrontmatterClassification(BODY, False, False, 0.0, "empty")
    prose = bool(_BODY_SENTENCE.search(value)) or _looks_like_prose(value)
    affiliation = bool(_AFFILIATION.search(value))
    if affiliation and not prose and len(value.split()) <= _AFFILIATION_MAX_WORDS:
        return FrontmatterClassification(
            AFFILIATION, True, False, 0.95, "organization/address markers; preserve source"
        )
    names = _NAME.findall(value)
    degree = bool(_DEGREE.search(value))
    # PLAN-080a：正文句里出现的邮箱或 "corresponding" 不是署名标记；ORCID 足够强，保留无条件判定。
    explicit_author = bool(
        _ORCID.search(value)
        or (
            not prose
            and (
                _CORRESPONDING.search(value)
                or (_EMAIL.search(value) and (names or "author" in value.casefold()))
            )
        )
    )
    signature = bool(_SIGNATURE.search(value))
    titled_name = bool(_PERSON_TITLE.search(value)) and len(names) >= 1 and not prose
    author_shape = explicit_author or signature or titled_name or (len(names) >= 2 and degree) or (
        len(names) == 1 and degree and not prose and len(value.split()) <= 18
    )
    if author_shape:
        reason = (
            "explicit author marker" if explicit_author
            else "signature block" if signature
            else "titled person name" if titled_name
            else "names and credentials"
        )
        return FrontmatterClassification(AUTHOR, True, False, 0.95, reason)
    return FrontmatterClassification(BODY, False, False, 0.0, "no front-matter signal")


def paragraph_role(text: str | None) -> str:
    return classify_frontmatter_text(text).role


def paragraph_is_author(text: str | None) -> bool:
    return classify_frontmatter_text(text).role == AUTHOR
