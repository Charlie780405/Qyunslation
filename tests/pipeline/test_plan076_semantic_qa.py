from __future__ import annotations

import pytest

from qyunslation.pipeline.ad_semantic import (
    parse_semantic_review,
    repair_once,
    select_high_risk_segments,
)


def test_selector_prioritizes_ad_risk_segments():
    segments = [
        {"id": "1", "source": "The weather was recorded."},
        {"id": "2", "source": "Patients received dupilumab 300 mg and no serious adverse events."},
    ]
    selected = select_high_risk_segments(segments)
    assert [item["id"] for item in selected] == ["2"]


def test_semantic_review_schema_is_strict():
    review = parse_semantic_review(
        '{"items":[{"id":"2","severity":"major","code":"NEGATION","message":"negation drift"}]}'
    )
    assert review[0].code == "NEGATION"
    with pytest.raises(ValueError, match="schema"):
        parse_semantic_review('{"items":[{"id":"2","severity":"critical","code":"X"}]}')


def test_repair_once_protects_facts_and_never_retries():
    calls = []

    def fixer(source, target, issues):
        calls.append(1)
        return "患者接受了度普利尤单抗 300 mg。"

    result = repair_once(
        source="Patients received dupilumab 300 mg.",
        target="患者接受了某药物 30 mg。",
        issues=[{"code": "AD_TERM_MISSING"}],
        repair_fn=fixer,
    )
    assert result.target == "患者接受了度普利尤单抗 300 mg。"
    assert result.attempts == 1
    assert calls == [1]
