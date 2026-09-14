# SPDX-License-Identifier: MPL-2.0
"""PLAN-058：可注入翻译路径的术语策略包与译后 QA。"""
from __future__ import annotations

from hashlib import sha256
from typing import Iterable

from qyunslation.glossary.resolver import TermMatch


def compile_term_policy(
    matches: Iterable[TermMatch], *, termbase_version: str | None = None
) -> dict:
    """Compile resolver matches into a JSON-safe, read-only task policy.

    Exact/alias matches from approved terms are hard constraints.  Semantic
    suggestions remain visible to reviewers but cannot silently change output.
    """
    terms = []
    seen: set[tuple[str, int, int, str]] = set()
    for match in matches:
        key = (match.concept_id, match.start, match.end, match.target_term)
        if key in seen:
            continue
        seen.add(key)
        hard = match.match_type in {"exact", "alias"} and match.confidence >= 0.99
        terms.append(
            {
                "concept_id": match.concept_id,
                "source_term": match.source_term,
                "preferred_target": match.target_term,
                "match_type": match.match_type,
                "term_type": match.term_type,
                "do_not_translate": match.do_not_translate,
                "forbidden_targets": list(match.forbidden_targets),
                "scope": match.layer,
                "confidence": match.confidence,
                "source_locations": [{"start": match.start, "end": match.end}],
                "hard_constraint": hard,
            }
        )
    terms.sort(key=lambda item: (item["source_locations"][0]["start"], item["source_term"]))
    return {
        "schema": "058-term-policy-v1",
        "termbase_version": termbase_version,
        "terms": terms,
    }


def policy_to_glossary(policy: dict | None) -> dict[str, str]:
    """Return only approved hard constraints for legacy translator adapters."""
    if not policy:
        return {}
    result: dict[str, str] = {}
    for term in policy.get("terms", []):
        if not term.get("hard_constraint"):
            continue
        source = str(term.get("source_term") or "").strip()
        target = str(term.get("preferred_target") or "").strip()
        if source and target and source not in result:
            result[source] = target
    return result


def policy_prompt(policy: dict | None, *, to_lang: str = "中文") -> str:
    """Render hard constraints without exposing the whole termbase."""
    from qyunslation.extensions.glossary_db import build_glossary_prompt

    return build_glossary_prompt(policy_to_glossary(policy), to_lang=to_lang)


def _count_occurrences(haystack: str, needle: str) -> int:
    needle = needle.casefold().strip()
    if not needle:
        return 0
    return haystack.casefold().count(needle)


def validate_term_policy(
    source_text: str, target_text: str, policy: dict | None
) -> list[dict]:
    """Check hard terms after translation and return locatable QA findings."""
    if not policy:
        return []
    source = source_text or ""
    target = target_text or ""
    findings: list[dict] = []
    for term in policy.get("terms", []):
        if not term.get("hard_constraint"):
            continue
        source_term = str(term.get("source_term") or "").strip()
        preferred = str(term.get("preferred_target") or "").strip()
        expected_count = _count_occurrences(source, source_term)
        if expected_count <= 0:
            continue
        actual_count = _count_occurrences(target, preferred)
        # 中文替代译法可能包含首选译法（如“主要终点评估”包含“主要终点”）。
        # 先扣除被明确列为禁用译法的命中，避免把错误译法误判为合规。
        forbidden_targets = [
            str(value).strip() for value in term.get("forbidden_targets") or [] if str(value).strip()
        ]
        for forbidden in forbidden_targets:
            if preferred.casefold() in forbidden.casefold():
                actual_count = max(
                    0, actual_count - _count_occurrences(target, forbidden)
                )
        if actual_count < expected_count:
            findings.append(
                {
                    "code": "TERM_MISSING_TARGET",
                    "severity": "error",
                    "concept_id": term.get("concept_id"),
                    "source_term": source_term,
                    "expected_target": preferred,
                    "expected_count": expected_count,
                    "actual_count": actual_count,
                }
            )
        for forbidden in forbidden_targets:
            if forbidden and _count_occurrences(target, forbidden):
                findings.append(
                    {
                        "code": "TERM_FORBIDDEN_TARGET",
                        "severity": "error",
                        "concept_id": term.get("concept_id"),
                        "source_term": source_term,
                        "forbidden_target": forbidden,
                    }
                )
    return findings


def policy_cache_key(
    *,
    tenant_id: str,
    project_id: str | None,
    src_lang: str,
    tgt_lang: str,
    termbase_version: str,
    source_sha256: str,
) -> str:
    """Build a cache key that cannot reuse output across termbase scopes."""
    parts = (
        tenant_id,
        project_id or "-",
        src_lang.casefold(),
        tgt_lang.casefold(),
        termbase_version,
        source_sha256,
    )
    return "term-policy:" + "|".join(parts)
