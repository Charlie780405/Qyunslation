"""PLAN-076e/076i: deterministic, direction-aware AD translation QA."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Mapping

from qyunslation.pipeline.qa.engine import QaFinding


@dataclass(frozen=True)
class QaContext:
    source: str
    target: str
    direction: str
    terms: Mapping[str, str] = field(default_factory=dict)


_FULLWIDTH_TRANS = str.maketrans("０１２３４５６７８９，．", "0123456789,.")

_NUMBER_RE = re.compile(
    r"(?<![A-Za-z])"
    r"(?:≥|≤|±)?\s*"
    r"\d+(?:[.,]\d+)?"
    r"(?:\s*[-–]\s*\d+(?:[.,]\d+)?)?"
    r"(?:\s*(?:mg|μg|mcg|g|mL|ml|%))?"
    r"(?![A-Za-z])"
)
_CJK_SCALE_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?\s*[万亿]")
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_NEGATION = re.compile(
    r"\b(?:no|not|without|never|neither|nor|failed to|did not|cannot|must not)\b"
    r"|无|未|不|非|否认|不得|禁止|不能|未见"
)
_MODALITY = {
    "prohibition": re.compile(r"\b(?:must not|shall not|cannot|prohibited)\b|不得|禁止|不能|不应"),
    "obligation": re.compile(r"\b(?:must|shall|required to|should)\b|必须|应当|应", re.I),
    "permission": re.compile(r"\b(?:may|can|permitted to|allowed to)\b|可以|可|允许", re.I),
}


def _normalize_numeric_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "")
    value = value.translate(_FULLWIDTH_TRANS)
    value = value.replace("μg", "mcg").replace("µg", "mcg")
    return value


def _numbers(text: str) -> list[str]:
    normalized = _normalize_numeric_text(text)
    found: list[str] = []
    for match in _NUMBER_RE.finditer(normalized):
        token = match.group(0).replace(",", "").replace(" ", "")
        if _YEAR_RE.fullmatch(token.strip("≥≤±")):
            continue
        found.append(token)
    for match in _CJK_SCALE_RE.finditer(normalized):
        found.append(match.group(0).replace(" ", ""))
    return found


def _modality(text: str) -> str | None:
    for name, pattern in _MODALITY.items():
        if pattern.search(text or ""):
            return name
    return None


def _finding(code: str, message: str, *, evidence: dict | None = None, severity: str = "blocker") -> QaFinding:
    return QaFinding(category="ad", severity=severity, code=code, message=message, evidence=evidence or {})


def run_ad_deterministic_qa(context: QaContext) -> list[QaFinding]:
    findings: list[QaFinding] = []
    source = context.source or ""
    target = context.target or ""

    source_numbers, target_numbers = _numbers(source), _numbers(target)
    if source_numbers != target_numbers:
        findings.append(
            _finding(
                "AD_NUMBER_DRIFT",
                "保护性数字、剂量或统计量在译文中发生变化",
                evidence={"source": source_numbers, "target": target_numbers},
            )
        )

    folded_target = _normalize_numeric_text(target).casefold()
    folded_source = _normalize_numeric_text(source).casefold()
    for source_term, target_term in context.terms.items():
        if source_term and source_term.casefold() in folded_source and target_term.casefold() not in folded_target:
            findings.append(
                _finding(
                    "AD_TERM_MISSING",
                    f"批准术语未按策略出现：{source_term} → {target_term}",
                    evidence={"source_term": source_term, "expected_target": target_term},
                )
            )

    source_negative = bool(_NEGATION.search(source))
    target_negative = bool(_NEGATION.search(target))
    if source_negative != target_negative:
        findings.append(
            _finding(
                "AD_NEGATION_DRIFT",
                "否定语义在译文中发生变化",
                evidence={"source_negative": source_negative, "target_negative": target_negative},
            )
        )

    source_modality, target_modality = _modality(source), _modality(target)
    if source_modality and target_modality and source_modality != target_modality:
        findings.append(
            _finding(
                "AD_MODALITY_DRIFT",
                "义务、许可或禁止情态在译文中发生变化",
                evidence={"source_modality": source_modality, "target_modality": target_modality},
            )
        )
    elif source_modality == "prohibition" and target_modality != "prohibition":
        findings.append(
            _finding(
                "AD_MODALITY_DRIFT",
                "禁止性约束未保留",
                evidence={"source_modality": source_modality, "target_modality": target_modality},
            )
        )

    return findings


def _contains(text: str, term: str) -> bool:
    if not term:
        return False
    if any(ord(char) > 127 for char in term):
        return term in text
    return bool(re.search(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", text, re.I))
