# SPDX-License-Identifier: MPL-2.0
"""PLAN-060 bilingual term evidence and conservative candidate extraction."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from qyunslation.glossary.candidate_rules import (
    classify_risk_by_rules,
    classify_term_type,
    load_rules,
    should_exclude_from_termbase,
)

_SCREEN_ABBREV = re.compile(r"\b[A-Z]{3,}(?:-[A-Z0-9]+)*\b")
_MORPH_TYPES = frozenset({"drug", "target", "code", "study_id", "medicine"})

_REFERENCE_ROLES = frozenset({"reference", "references", "bibliography", "citation", "preserve"})


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
    return classify_risk_by_rules(source_term, term_type)


def _synthetic_terms(source: str) -> Iterable[str]:
    """Extract only conservative morphological candidates."""
    rules = load_rules()
    yielded: set[str] = set()
    for name, pattern in rules.include_patterns:
        if name not in _MORPH_TYPES:
            continue
        for match in pattern.finditer(source or ""):
            value = match.group(0).strip()
            excluded, _reason = should_exclude_from_termbase(value, rules=rules)
            if value and value not in yielded and not excluded:
                yielded.add(value)
                yield value


def collect_abbrev_candidates(source: str) -> list[str]:
    """Abbreviation-shaped tokens that need screening, not auto-enqueue."""
    rules = load_rules()
    morph = set(_synthetic_terms(source))
    found: list[str] = []
    for match in _SCREEN_ABBREV.finditer(source or ""):
        value = match.group(0).strip()
        excluded, _reason = should_exclude_from_termbase(value, rules=rules)
        if value and value not in morph and not excluded and value not in found:
            found.append(value)
    return found


def extract_term_pairs(evidence: Iterable[BilingualTermEvidence]) -> list[dict]:
    """Return aligned candidate pairs without fabricating unaligned targets.

    Workflow adapters should supply ``source_term``/``target_term`` for tables,
    footnotes, OCR overlays and native Office shapes.  The fallback only emits
    strongly-shaped codes and medical terms, and leaves their target empty when
    no reliable span was supplied.
    """
    rows, _stats = extract_term_pairs_with_stats(evidence)
    return rows


def extract_term_pairs_with_stats(
    evidence: Iterable[BilingualTermEvidence],
) -> tuple[list[dict], dict[str, int]]:
    rows: list[dict] = []
    stats: dict[str, int] = {}
    rules = load_rules()
    for item in evidence:
        if not item.is_translatable:
            continue
        explicit_source = (item.source_term or "").strip()
        if explicit_source:
            excluded, reason = should_exclude_from_termbase(explicit_source, rules=rules)
            if excluded:
                stats[reason] = stats.get(reason, 0) + 1
                continue
            rows.append(
                {
                    "source_term": explicit_source,
                    "observed_target": (item.target_term or item.target_text).strip(),
                    "term_type": item.term_type or classify_term_type(explicit_source),
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
                    "term_type": item.term_type or classify_term_type(source_term),
                    "source_context": item.source_text[:1000],
                    "target_context": item.target_text[:1000],
                    "occurrences": [item.occurrence()],
                }
            )
    return rows, stats
