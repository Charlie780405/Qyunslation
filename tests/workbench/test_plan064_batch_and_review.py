# SPDX-License-Identifier: MPL-2.0
"""PLAN-064：批量拒绝放宽；已批准列表排序。"""
from qyunslation.persist.candidate_repo import sort_review_candidates


def test_sort_review_candidates_puts_frequent_new_terms_first():
    rows = [
        {
            "source_term": "NHS",
            "match_type": "exact",
            "risk": "high",
            "occurrences": [{}, {}],
        },
        {
            "source_term": "rare",
            "match_type": "llm",
            "risk": "normal",
            "occurrences": [{}],
        },
        {
            "source_term": "hot",
            "match_type": "candidate",
            "risk": "normal",
            "occurrences": [{}, {}, {}],
        },
    ]
    ranked = [row["source_term"] for row in sort_review_candidates(rows)]
    assert ranked == ["hot", "rare", "NHS"]
