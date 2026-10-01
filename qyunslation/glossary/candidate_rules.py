# SPDX-License-Identifier: MPL-2.0
"""PLAN-061：术语候选准入规则（可复用、可进化）。"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from qyunslation.glossary.governance import is_junk_source, normalize_source
from qyunslation.structure.models import TranslationPolicy
from qyunslation.structure.table_cell_policy import classify_cell_policy

EXCLUDE_EMPTY = "EMPTY"
EXCLUDE_CELL_PRESERVE = "CELL_PRESERVE"
EXCLUDE_PATTERN = "PATTERN"
EXCLUDE_DENYLIST = "DENYLIST"
EXCLUDE_TOO_SHORT = "TOO_SHORT"
EXCLUDE_TOO_LONG = "TOO_LONG"
EXCLUDE_JUNK = "JUNK"
EXCLUDE_FRAGMENT = "FRAGMENT"
EXCLUDE_REJECTED = "REJECTED"
_GENERIC_SHORT_TERMS = frozenset(
    {
        "no",
        "yes",
        "n/a",
        "na",
        "pp",
        "id",
        "or",
        "ad",
        "it",
        "is",
        "as",
        "at",
        "by",
        "in",
        "of",
        "on",
        "to",
        "vs",
    }
)
_HIGH_RISK_ABBREVIATIONS = frozenset({"nhs", "icu"})
_DRUG_FRAGMENT = re.compile(r"^[a-z]{1,3}(?:mab|nib|cept)$", re.I)
_ORG_HINT = re.compile(
    r"\b(?:hospital|university|institute|biotech|pharma(?:ceutical)?)\b",
    re.I,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES = ROOT / "glossaries" / "term-candidate-rules.toml"
DEFAULT_EXCLUSIONS = ROOT / "glossaries" / "term-exclusions.csv"


@dataclass(frozen=True, slots=True)
class CandidateRules:
    version: str
    min_source_chars: int
    max_source_chars: int
    min_drug_chars: int
    delegate_cell_preserve: bool
    exclude_patterns: tuple[re.Pattern[str], ...]
    denylist: frozenset[str]
    include_patterns: tuple[tuple[str, re.Pattern[str]], ...]
    high_types: frozenset[str]
    abbreviation_is_high: bool


def _compile_patterns(values: list[str] | None) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(item, re.I) for item in values or ())


def _load_exclusion_denylist(path: Path) -> frozenset[str]:
    if not path.is_file():
        return frozenset()
    denied: set[str] = set()
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            source = normalize_source(row.get("source") or "")
            if source:
                denied.add(source)
    return frozenset(denied)


@lru_cache(maxsize=4)
def load_rules(path: str | None = None) -> CandidateRules:
    rules_path = Path(path) if path else DEFAULT_RULES
    data = tomllib.loads(rules_path.read_text(encoding="utf-8"))
    thresholds = data.get("thresholds") or {}
    exclude = data.get("exclude") or {}
    include = data.get("include") or {}
    risk = data.get("risk") or {}
    denylist = {normalize_source(item) for item in exclude.get("denylist") or [] if item}
    denylist.update(_load_exclusion_denylist(DEFAULT_EXCLUSIONS))
    casefold_includes = {"drug", "medicine", "organization", "target"}
    include_patterns = tuple(
        (
            name,
            re.compile(pattern, re.I if name in casefold_includes else 0),
        )
        for name, pattern in include.items()
        if pattern
    )
    return CandidateRules(
        version=str(data.get("version") or "unknown"),
        min_source_chars=int(thresholds.get("min_source_chars") or 3),
        max_source_chars=int(thresholds.get("max_source_chars") or 64),
        min_drug_chars=int(thresholds.get("min_drug_chars") or 6),
        delegate_cell_preserve=bool(exclude.get("delegate_cell_preserve", True)),
        exclude_patterns=_compile_patterns(exclude.get("patterns")),
        denylist=frozenset(denylist),
        include_patterns=include_patterns,
        high_types=frozenset(
            str(item).strip().casefold()
            for item in risk.get("high_types") or ()
            if str(item).strip()
        ),
        abbreviation_is_high=bool(risk.get("abbreviation_is_high", True)),
    )


def rules_version(path: str | None = None) -> str:
    return load_rules(path).version


def rules_fingerprint(path: str | None = None) -> str:
    """denylist / patterns / include 内容哈希；version 本身不参与。"""
    current = load_rules(path)
    payload = {
        "denylist": sorted(current.denylist),
        "patterns": [item.pattern for item in current.exclude_patterns],
        "include": [(name, item.pattern) for name, item in current.include_patterns],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def include_hit(text: str, *, rules: CandidateRules | None = None) -> str | None:
    source = (text or "").strip()
    if not source:
        return None
    current = rules or load_rules()
    for name, pattern in current.include_patterns:
        if pattern.search(source):
            return name
    return None


def classify_term_type(text: str, *, rules: CandidateRules | None = None) -> str:
    return include_hit(text, rules=rules) or "general"


def should_exclude_from_termbase(
    text: str, *, rules: CandidateRules | None = None
) -> tuple[bool, str]:
    """返回 (是否排除, 原因码)。原因码进 run 统计，供 PLAN-063 归纳新规则。"""
    current = rules or load_rules()
    source = (text or "").strip()
    if not source:
        return True, EXCLUDE_EMPTY
    normalized = normalize_source(source)
    if normalized in current.denylist:
        return True, EXCLUDE_DENYLIST
    hit = include_hit(source, rules=current)
    if _DRUG_FRAGMENT.fullmatch(source):
        return True, EXCLUDE_FRAGMENT
    if not hit and len(source) < current.min_source_chars:
        return True, EXCLUDE_TOO_SHORT
    if len(source) > current.max_source_chars:
        return True, EXCLUDE_TOO_LONG
    for pattern in current.exclude_patterns:
        if pattern.fullmatch(source):
            return True, EXCLUDE_PATTERN
    if current.delegate_cell_preserve:
        if classify_cell_policy(source) is TranslationPolicy.PRESERVE:
            return True, EXCLUDE_CELL_PRESERVE
    if is_junk_source(source):
        return True, EXCLUDE_JUNK
    return False, ""


def classify_risk_by_rules(
    text: str, term_type: str | None = None, *, rules: CandidateRules | None = None
) -> str:
    current = rules or load_rules()
    source = (text or "").strip()
    normalized_type = (term_type or "").strip().casefold()
    if source.casefold() in _HIGH_RISK_ABBREVIATIONS:
        return "high"
    if normalized_type in current.high_types:
        return "high"
    hit = include_hit(source, rules=current) or normalized_type
    if hit in {"drug", "target", "organization", "study_id", "code", "protocol"}:
        return "high"
    if current.abbreviation_is_high:
        if hit in {"study_id", "code", "protocol"}:
            return "high"
        if hit == "abbreviation" or normalized_type == "abbreviation":
            if source.casefold() in _GENERIC_SHORT_TERMS:
                return "normal"
            return "high"
        if re.fullmatch(r"[A-Z]{2,}(?:-[A-Z0-9]+)*", source):
            if source.casefold() in _GENERIC_SHORT_TERMS:
                return "normal"
            if hit in {"drug", "target", "organization"}:
                return "high"
            return "normal"
    if _ORG_HINT.search(source):
        return "high"
    if source and len(source) < current.min_source_chars:
        if hit in {"drug", "target", "organization", "study_id", "code", "protocol"}:
            return "high"
        return "normal"
    return "normal"
