# SPDX-License-Identifier: MPL-2.0
"""PLAN-064：推荐译法先走词库/词干，再才 LLM。"""
from qyunslation.workbench.term_align import (
    MATCH_ALIAS,
    MATCH_NONE,
    MATCH_TERMBASE,
    AlignedTerm,
    suggest_from_termbase,
)


def test_suggest_from_termbase_uses_exact_policy_then_stem_alias():
    policy = {
        "terms": [
            {
                "source_term": "tralokinumab",
                "preferred_target": "曲罗芦单抗",
                "hard_constraint": True,
            }
        ]
    }
    exact = suggest_from_termbase(
        [AlignedTerm("tralokinumab", "", None, MATCH_NONE, 0.0)],
        policy=policy,
    )
    assert exact["tralokinumab"].match_type == MATCH_TERMBASE
    assert exact["tralokinumab"].suggested_target == "曲罗芦单抗"

    alias = suggest_from_termbase(
        [AlignedTerm("anti-tralokinumab", "", None, MATCH_NONE, 0.0)],
        policy=policy,
    )
    assert alias["anti-tralokinumab"].match_type == MATCH_ALIAS
    assert alias["anti-tralokinumab"].suggested_target == "曲罗芦单抗"


def test_suggest_from_termbase_skips_llm_when_lexicon_hits():
    policy = {
        "terms": [
            {
                "source_term": "tralokinumab",
                "preferred_target": "曲罗芦单抗",
                "hard_constraint": True,
            }
        ]
    }
    found = suggest_from_termbase(
        [AlignedTerm("unknown-term", "", None, MATCH_NONE, 0.0)],
        policy=policy,
    )
    assert found == {}
