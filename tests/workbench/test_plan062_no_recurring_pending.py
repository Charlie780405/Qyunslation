# SPDX-License-Identifier: MPL-2.0
"""PLAN-062d：已 curated 词跨 job 不再进入待确认。"""
from __future__ import annotations

from qyunslation.workbench.bridge import _extract_candidates, _is_applied
from qyunslation.workbench.evidence import BilingualTermEvidence


def test_is_applied_reports_missed_preferred_target():
    evidence = BilingualTermEvidence(
        source_text="The primary endpoint was met.",
        target_text="终点再次达到。",
    )
    applied, preferred = _is_applied(
        {
            "terms": [
                {
                    "source_term": "primary endpoint",
                    "preferred_target": "主要终点评估",
                    "hard_constraint": True,
                }
            ]
        },
        evidence,
        "primary endpoint",
    )
    assert applied is False
    assert preferred == "主要终点评估"
