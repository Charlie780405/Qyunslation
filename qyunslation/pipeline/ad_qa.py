"""PLAN-076e: deterministic, direction-aware AD translation QA."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping

from qyunslation.pipeline.qa.engine import QaFinding


@dataclass(frozen=True)
class QaContext:
    source: str
    target: str
    direction: str
    terms: Mapping[str, str] = field(default_factory=dict)


_NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)?(?:\s*[-–]\s*\d+(?:[.,]\d+)?)?(?![A-Za-z])")
_NEGATION = re.compile(r"\b(?:no|not|without|never|neither|nor|failed to|did not|cannot|must not)\b|无|未|不|否认|不得|禁止|不能|未见")
_MODALITY = {
    "prohibition": re.compile(r"\b(?:must not|shall not|cannot|prohibited)\b|不得|禁止|不能|不应"),
    "obligation": re.compile(r"\b(?:must|shall|required to|should)\b|必须|应当|应", re.I),
    "permission": re.compile(r"\b(?:may|can|permitted to|allowed to)\b|可以|可|允许", re.I),
}


def _numbers(text: str) -> list[str]:
    return [item.replace(",", "").replace(" ", "") for item in _NUMBER_RE.findall(text or "")]


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
    direction = (context.direction or "").strip().casefold()

    source_numbers, target_numbers = _numbers(source), _numbers(target)
    if source_numbers != target_numbers:
        findings.append(_finding("AD_NUMBER_DRIFT", "保护性数字、剂量或统计量在译文中发生变化", evidence={"source": source_numbers, "target": target_numbers}))

    folded_target = target.casefold()
    for source_term, target_term in context.terms.items():
        if source_term and source_term.casefold() in source.casefold() and target_term.casefold() not in folded_target:
            findings.append(_finding("AD_TERM_MISSING", f"批准术语未按策略出现：{source_term} → {target_term}", evidence={"source_term": source_term, "expected_target": target_term}))

    source_negative = bool(_NEGATION.search(source))
    target_negative = bool(_NEGATION.search(target))
    if source_negative != target_negative:
        findings.append(_finding("AD_NEGATION_DRIFT", "否定语义在译文中发生变化", evidence={"source_negative": source_negative, "target_negative": target_negative}))

    source_modality, target_modality = _modality(source), _modality(target)
    if source_modality and target_modality and source_modality != target_modality:
        findings.append(_finding("AD_MODALITY_DRIFT", "义务、许可或禁止情态在译文中发生变化", evidence={"source_modality": source_modality, "target_modality": target_modality}))
    elif source_modality == "prohibition" and target_modality != "prohibition":
        findings.append(_finding("AD_MODALITY_DRIFT", "禁止性约束未保留", evidence={"source_modality": source_modality, "target_modality": target_modality}))

    return findings
