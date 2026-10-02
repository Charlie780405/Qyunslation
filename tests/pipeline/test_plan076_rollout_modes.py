from __future__ import annotations

from qyunslation.pipeline.ad_runtime import ad_rollout_allowed, ad_rollout_mode


def test_shadow_mode_is_fail_closed_for_user_tasks():
    assert ad_rollout_mode(env="production", configured="shadow") == "shadow"
    assert not ad_rollout_allowed(mode="shadow", tenant="pilot", tenants="pilot")


def test_default_mode_maps_to_off():
    assert ad_rollout_mode(env="production", configured="default") == "off"


def test_pilot_requires_allowlist_even_in_development():
    assert ad_rollout_allowed(mode="pilot", tenant="pilot", tenants="pilot,research")
    assert not ad_rollout_allowed(mode="pilot", tenant="pilot", tenants=None)
