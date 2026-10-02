from __future__ import annotations

from qyunslation.pipeline.ad_semantic import orchestrate_ad_semantic_qa


def test_semantic_orchestrator_shadow_skips_reviewer():
    result = orchestrate_ad_semantic_qa(
        source="Patients received dupilumab 300 mg and no adverse events.",
        target="患者接受了度普利尤单抗 300 mg，未见不良事件。",
        mode="shadow",
        reviewer_url="http://127.0.0.1:9999/review",
    )
    assert result["mode"] == "shadow"
    assert result["issues"] == []
    assert not result["degraded"]


def test_semantic_orchestrator_required_without_reviewer_degrades():
    result = orchestrate_ad_semantic_qa(
        source="Patients received dupilumab.",
        target="患者接受了度普利尤单抗。",
        mode="required",
        reviewer_url=None,
    )
    assert result["degraded"] is True
