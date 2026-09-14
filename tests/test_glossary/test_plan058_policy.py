# SPDX-License-Identifier: MPL-2.0
"""PLAN-058：术语策略包及译后术语 QA。"""
from __future__ import annotations

from qyunslation.glossary.resolver import TermMatch
from qyunslation.glossary.term_policy import (
    compile_term_policy,
    evaluate_term_policy,
    policy_cache_key,
    policy_to_glossary,
    validate_term_policy,
)
from qyunslation.glossary.ssot import apply_term_policy_to_payload


def _match(**kwargs):
    values = {
        "concept_id": "c1",
        "source_term": "primary endpoint",
        "target_term": "主要终点",
        "start": 0,
        "end": 16,
        "match_type": "exact",
        "layer": "project",
        "role": "preferred",
        "term_type": "endpoint",
        "confidence": 1.0,
        "do_not_translate": False,
        "forbidden_targets": ("主要终点评估",),
    }
    values.update(kwargs)
    return TermMatch(**values)


def test_compile_policy_marks_exact_as_hard_and_preserves_locations():
    policy = compile_term_policy([_match()], termbase_version="058-v1")
    assert policy["termbase_version"] == "058-v1"
    assert policy["terms"][0]["hard_constraint"] is True
    assert policy["terms"][0]["source_locations"] == [{"start": 0, "end": 16}]
    assert policy_to_glossary(policy) == {"primary endpoint": "主要终点"}


def test_validate_policy_reports_missing_and_forbidden_translation():
    policy = compile_term_policy([_match()])
    findings = validate_term_policy(
        "The primary endpoint was recorded.",
        "记录了主要终点评估。",
        policy,
    )
    assert {finding["code"] for finding in findings} == {
        "TERM_MISSING_TARGET",
        "TERM_FORBIDDEN_TARGET",
    }
    assert validate_term_policy(
        "The primary endpoint was recorded.", "记录了主要终点。", policy
    ) == []


def test_semantic_suggestion_is_not_hard_constraint():
    policy = compile_term_policy([_match(match_type="semantic", confidence=0.72)])
    assert policy["terms"][0]["hard_constraint"] is False
    assert policy_to_glossary(policy) == {}


def test_cache_key_changes_when_scope_or_termbase_changes():
    first = policy_cache_key(
        tenant_id="t1", project_id="p1", src_lang="en", tgt_lang="zh", termbase_version="v1", source_sha256="a" * 64
    )
    second = policy_cache_key(
        tenant_id="t1", project_id="p1", src_lang="en", tgt_lang="zh", termbase_version="v2", source_sha256="a" * 64
    )
    assert first != second
    assert "t1" in first and "p1" in first and "v1" in first


def test_evaluate_term_policy_returns_machine_readable_gate_result():
    policy = {
        "terms": [
            {
                "concept_id": "c1",
                "source_term": "primary endpoint",
                "preferred_target": "主要终点评估",
                "hard_constraint": True,
            }
        ]
    }
    result = evaluate_term_policy(
        "The primary endpoint was met.", "主要终点已达到。", policy
    )
    assert result["available"] is True
    assert result["passed"] is False
    assert result["finding_count"] == 1
    assert result["findings"][0]["code"] == "TERM_MISSING_TARGET"


def test_policy_injection_overrides_conflicting_legacy_glossary_only_for_hard_terms():
    class Payload:
        glossary_dict = {"primary endpoint": "旧译法", "clinical trial": "临床试验"}

    payload = Payload()
    policy = compile_term_policy([_match()])
    merged = apply_term_policy_to_payload(payload, policy)
    assert merged["primary endpoint"] == "主要终点"
    assert merged["clinical trial"] == "临床试验"
