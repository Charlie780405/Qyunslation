"""PLAN-076 runtime glue shared by API and legacy translation workflows."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from qyunslation.pipeline.ad_prompt import PromptContext, compile_prompt

QA_RULE_VERSION = "076-qa-v1"


def ad_rollout_mode(*, env: str | None, configured: str | None) -> str:
    value = (configured or "").strip().casefold()
    if value == "default":
        value = "off"
    if value in {"off", "shadow", "pilot"}:
        return value
    return "off" if (env or "development").strip().casefold() == "production" else "pilot"


def ad_rollout_tenants(raw: str | None) -> frozenset[str]:
    return frozenset(
        item.strip().casefold()
        for item in (raw or "").replace(";", ",").split(",")
        if item.strip()
    )


def ad_rollout_allowed(*, mode: str, tenant: str, tenants: str | None) -> bool:
    normalized_tenant = (tenant or "").strip().casefold()
    if mode == "off" or not normalized_tenant:
        return False
    if mode == "shadow":
        return False
    if mode == "pilot":
        allowlist = ad_rollout_tenants(tenants)
        return normalized_tenant in allowlist
    return False


def _direction_code(direction: str, target_language: str | None = None) -> str:
    value = (direction or "").strip()
    if value in {"English → 简体中文", "en-zh"}:
        return "en-zh"
    if value in {"简体中文 → English", "zh-en"}:
        return "zh-en"
    target = (target_language or "").strip().casefold()
    if target in {"english", "en"}:
        return "zh-en"
    if target in {"简体中文", "中文", "chinese", "zh"}:
        return "en-zh"
    raise ValueError("unsupported translation direction for AD profile")


def compile_runtime_settings(
    settings: dict[str, Any] | None,
    *,
    termbase_version: str | None = None,
    model_profile_id: str | None = None,
) -> dict[str, Any]:
    current = deepcopy(settings or {})
    domain = str(current.get("domain_profile") or "general").strip().casefold()
    if domain != "ad":
        return current
    if str(current.get("custom_prompt") or "").strip():
        raise ValueError("AD profile forbids custom_prompt")
    direction = _direction_code(str(current.get("direction") or ""), current.get("target_language"))
    document = str(current.get("profile") or current.get("document_profile") or "").strip()
    compiled = compile_prompt(PromptContext(domain, direction, document, "translate"))
    current["custom_prompt"] = compiled.text
    snapshot = compiled.snapshot()
    snapshot["domain_profile"] = "ad"
    snapshot["termbase_version"] = termbase_version
    snapshot["qa_rule_version"] = QA_RULE_VERSION
    if model_profile_id:
        snapshot["model_profile_id"] = model_profile_id
    current["prompt_snapshot"] = snapshot
    return current
