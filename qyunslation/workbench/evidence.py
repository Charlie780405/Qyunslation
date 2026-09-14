# SPDX-License-Identifier: MPL-2.0
"""PLAN-060 bilingual term evidence and conservative candidate extraction."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

_REFERENCE_ROLES = frozenset({"reference", "references", "bibliography", "citation", "preserve"})
_HIGH_RISK_TYPES = frozenset(
    {"drug", "biologic", "product", "target", "dose", "organization", "protocol", "study_id"}
)
_ABBREVIATION = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)*\b")
_CODE = re.compile(r"\b[A-Z]{2,}[A-Z0-9]*(?:-[A-Z0-9]+)+\b")
_DOSE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg|g|µg|ug|mcg|mL|ml|IU|%)\b", re.I)
_MEDICINE = re.compile(r"\b[a-z][a-z-]*(?:mab|nib|cept|itis|emia|osis)\b", re.I)


@dataclass(frozen=True, slots=True)
class BilingualTermEvidence:
    source_text: str
    target_text: str
    role: str = "body"
    page_no: int | None = None
    block_id: str | None = None
    object_id: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    bbox: dict | None = None
    source_term: str | None = None
    target_term: str | None = None
    term_type: str | None = None

    @property
    def is_translatable(self) -> bool:
        return self.role.strip().casefold() not in _REFERENCE_ROLES

    def occurrence(self) -> dict:
        return {
            "page_no": self.page_no,
            "block_id": self.block_id,
            "object_id": self.object_id,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "bbox": self.bbox,
            "source_context": self.source_text[:1000],
            "target_context": self.target_text[:1000],
        }


def classify_risk(source_term: str, term_type: str | None = None) -> str:
    """Classify terms that require an administrator before publication."""
    normalized_type = (term_type or "").strip().casefold()
    source = (source_term or "").strip()
    if normalized_type in _HIGH_RISK_TYPES:
        return "high"
    if _CODE.fullmatch(source) or _DOSE.fullmatch(source):
        return "high"
    if _ABBREVIATION.fullmatch(source) and len(source) >= 3:
        return "high"
    if re.search(r"(?:mab|nib|cept)$", source, re.I):
        return "high"
    return "normal"


def _synthetic_terms(source: str) -> Iterable[str]:
    """Extract only conservative candidates when an adapter lacks term spans."""
    yielded: set[str] = set()
    for pattern in (_CODE, _DOSE, _ABBREVIATION, _MEDICINE):
        for match in pattern.finditer(source):
            value = match.group(0).strip()
            if value and value not in yielded:
                yielded.add(value)
                yield value


def extract_term_pairs(evidence: Iterable[BilingualTermEvidence]) -> list[dict]:
    """Return aligned candidate pairs without fabricating unaligned targets.

    Workflow adapters should supply ``source_term``/``target_term`` for tables,
    footnotes, OCR overlays and native Office shapes.  The fallback only emits
    strongly-shaped codes and medical terms, and leaves their target empty when
    no reliable span was supplied.
    """
    rows: list[dict] = []
    for item in evidence:
        if not item.is_translatable:
            continue
        explicit_source = (item.source_term or "").strip()
        if explicit_source:
            rows.append(
                {
                    "source_term": explicit_source,
                    "observed_target": (item.target_term or item.target_text).strip(),
                    "term_type": item.term_type or "general",
                    "source_context": item.source_text[:1000],
                    "target_context": item.target_text[:1000],
                    "occurrences": [item.occurrence()],
                }
            )
            continue
        for source_term in _synthetic_terms(item.source_text):
            rows.append(
                {
                    "source_term": source_term,
                    "observed_target": "",
                    "term_type": item.term_type or "general",
                    "source_context": item.source_text[:1000],
                    "target_context": item.target_text[:1000],
                    "occurrences": [item.occurrence()],
                }
            )
    return rows
