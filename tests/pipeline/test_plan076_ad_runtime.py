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


def test_ad_rollout_defaults_to_pilot_only_outside_production():
    assert ad_rollout_mode(env="development", configured=None) == "pilot"
    assert ad_rollout_mode(env="production", configured=None) == "off"
    assert ad_rollout_mode(env="production", configured="default") == "default"


def test_ad_rollout_pilot_is_tenant_scoped_in_production():
    assert ad_rollout_tenants("pilot;research") == frozenset({"pilot", "research"})
    assert ad_rollout_allowed(
        env="production", mode="pilot", tenant="pilot", tenants="pilot,research"
    )
    assert not ad_rollout_allowed(
        env="production", mode="pilot", tenant="other", tenants="pilot,research"
    )
    assert not ad_rollout_allowed(env="development", mode="pilot", tenant="pilot", tenants=None)
    assert not ad_rollout_allowed(env="production", mode="pilot", tenant="pilot", tenants=None)
