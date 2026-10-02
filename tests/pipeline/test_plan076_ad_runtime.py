from __future__ import annotations

import pytest

from qyunslation.pipeline.ad_runtime import compile_runtime_settings


def test_runtime_settings_compile_ad_prompt_snapshot_and_direction():
    settings = {
        "domain_profile": "ad",
        "direction": "简体中文 → English",
        "profile": "临床研究文档",
        "custom_prompt": "保持公司名称不变。",
    }
    result = compile_runtime_settings(settings)
    assert result["prompt_snapshot"]["profile_id"] == "ad.zh-en.clinical.translate.v1"
    assert result["prompt_snapshot"]["digest"].startswith("sha256:")
    assert "特应性皮炎" in result["custom_prompt"]
    assert "保持公司名称不变。" in result["custom_prompt"]


def test_runtime_settings_fail_closed_for_invalid_ad_profile():
    with pytest.raises(ValueError, match="unsupported AD document profile"):
        compile_runtime_settings({"domain_profile": "ad", "direction": "English → 简体中文", "profile": "监管申报材料"})
