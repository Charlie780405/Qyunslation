from __future__ import annotations

import pytest

from qyunslation.pipeline.ad_runtime import (
    ad_rollout_allowed,
    ad_rollout_mode,
    ad_rollout_tenants,
    compile_runtime_settings,
)


def test_runtime_settings_compile_ad_prompt_snapshot_and_direction():
    settings = {
        "domain_profile": "ad",
        "direction": "简体中文 → English",
        "profile": "临床研究文档",
    }
    result = compile_runtime_settings(settings, termbase_version="058-test", model_profile_id="test-model")
    assert result["prompt_snapshot"]["profile_id"] == "ad.zh-en.clinical.translate.v1"
    assert result["prompt_snapshot"]["digest"].startswith("sha256:")
    assert result["prompt_snapshot"]["termbase_version"] == "058-test"
    assert result["prompt_snapshot"]["model_profile_id"] == "test-model"
    assert "特应性皮炎" in result["custom_prompt"]


def test_runtime_settings_reject_custom_prompt_in_ad_mode():
    with pytest.raises(ValueError, match="custom_prompt"):
        compile_runtime_settings(
            {
                "domain_profile": "ad",
                "direction": "English → 简体中文",
                "profile": "医学研究文献",
                "custom_prompt": "保持公司名称不变。",
            }
        )


def test_runtime_settings_fail_closed_for_invalid_ad_profile():
    with pytest.raises(ValueError, match="unsupported AD document profile"):
        compile_runtime_settings({"domain_profile": "ad", "direction": "English → 简体中文", "profile": "监管申报材料"})


def test_ad_rollout_defaults_to_pilot_only_outside_production():
    assert ad_rollout_mode(env="development", configured=None) == "pilot"
    assert ad_rollout_mode(env="production", configured=None) == "off"
    assert ad_rollout_mode(env="production", configured="default") == "off"


def test_ad_rollout_pilot_is_tenant_scoped_in_production():
    assert ad_rollout_tenants("pilot;research") == frozenset({"pilot", "research"})
    assert ad_rollout_allowed(
        mode="pilot", tenant="pilot", tenants="pilot,research"
    )
    assert not ad_rollout_allowed(
        mode="pilot", tenant="other", tenants="pilot,research"
    )
    assert not ad_rollout_allowed(mode="pilot", tenant="pilot", tenants=None)
