# SPDX-License-Identifier: MPL-2.0
"""PLAN-079: every finding comes with concrete, clickable ways out, not just a description."""
from __future__ import annotations

from qyunslation.pipeline.qa import registry

KINDS = {"locate", "disposition", "revise", "recheck", "termbase"}


def test_every_blocking_or_warning_rule_has_exactly_one_recommended_way_out():
    for rule in registry.all_rules():
        remedies = registry.remedies_for(rule.code, rule.rule_class)
        if rule.rule_class == "I":
            assert remedies == []
            continue
        assert remedies, rule.code
        assert [r["recommended"] for r in remedies].count(True) == 1, rule.code
        assert {r["kind"] for r in remedies} <= KINDS, rule.code
        assert len({r["id"] for r in remedies}) == len(remedies), rule.code


def test_prefilled_reasons_meet_the_audit_minimum_and_use_actions_the_class_allows():
    for rule in registry.all_rules():
        for remedy in registry.remedies_for(rule.code, rule.rule_class):
            if remedy["kind"] != "disposition":
                continue
            assert len(remedy["reason"]) >= 10, (rule.code, remedy["id"])
            assert rule.rule_class in registry.ACTION_CLASSES[remedy["action"]], (rule.code, remedy["action"])


def test_the_way_out_depends_on_what_kind_of_problem_it_is():
    by_class = {
        "C1": ("AD_NUMBER_DRIFT", "revise"),         # a fact may be wrong: regenerate (or report a false positive)
        "C2": ("LOGO_MISSING", "disposition"),       # reviewer judgement: go ahead with a reason
        "C3": ("QA_ROUND_FAILED", "recheck"),        # the check did not run: run it again
        "C4": ("TERM_HIGH_RISK_CONFLICT", "termbase"),  # fix the vocabulary first
        "W": ("LATIN_RESIDUE", "disposition"),       # acknowledge
    }
    for rule_class, (code, kind) in by_class.items():
        recommended = next(r for r in registry.remedies_for(code, rule_class) if r["recommended"])
        assert recommended["kind"] == kind, (code, recommended)


def test_garbled_text_default_reason_says_what_was_checked():
    waive = next(r for r in registry.remedies_for("TEXT_ENCODING_ARTIFACT", "C2") if r["kind"] == "disposition")
    assert "页面" in waive["reason"] and waive["action"] == "grant_waiver"


def test_a_pending_false_positive_report_always_has_a_next_step():
    confirmer = registry.pending_report_remedies(True)
    assert [r["id"] for r in confirmer] == ["locate", "confirm", "reject", "revise"]
    assert next(r for r in confirmer if r["recommended"])["id"] == "confirm"
    waiting = registry.pending_report_remedies(False)
    assert waiting[0]["kind"] == "info" and "术语管理员" in waiting[0]["why"]
    assert next(r for r in waiting if r["recommended"])["kind"] == "revise"  # something clickable is recommended
    for remedy in confirmer:
        if remedy["kind"] == "disposition":
            assert len(remedy["reason"]) >= 10
