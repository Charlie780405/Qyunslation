from __future__ import annotations

from qyunslation.pipeline.ad_inspection import inspect_ad_text_pair


def test_ad_inspection_blocks_when_target_missing():
    findings, snapshot, degraded = inspect_ad_text_pair(
        source_text="Patients with atopic dermatitis received dupilumab.",
        target_text="",
        direction_label="English → 简体中文",
        settings_snapshot={"semantic_qa_mode": "shadow"},
    )
    assert not degraded
    assert snapshot["status"] == "unavailable"
    assert any(item.code == "AD_QA_SOURCE_UNAVAILABLE" for item in findings)
