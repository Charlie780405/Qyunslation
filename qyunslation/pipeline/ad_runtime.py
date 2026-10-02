"""PLAN-076 runtime glue shared by API and legacy translation workflows."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from qyunslation.pipeline.ad_prompt import PromptContext, compile_prompt


def ad_rollout_mode(*, env: str | None, configured: str | None) -> str:
    value = (configured or "").strip().casefold()
    if value in {"off", "shadow", "pilot", "default"}:
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
    if mode != "pilot":
        return True
    allowlist = ad_rollout_tenants(tenants)
    # Pilot is always tenant-scoped; an empty allowlist is fail-closed in every
    # environment, including development.
    return normalized_tenant in allowlist


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


def compile_runtime_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    current = deepcopy(settings or {})
    domain = str(current.get("domain_profile") or "general").strip().casefold()
    if domain != "ad":
        return current
    direction = _direction_code(str(current.get("direction") or ""), current.get("target_language"))
    document = str(current.get("profile") or current.get("document_profile") or "").strip()
    compiled = compile_prompt(PromptContext(domain, direction, document, "translate"))
    custom = str(current.get("custom_prompt") or "").strip()
    if custom.startswith(compiled.text):
        current["custom_prompt"] = custom
    else:
        current["custom_prompt"] = compiled.text + (f"\n\n附加任务约束：\n{custom}" if custom else "")
    current["prompt_snapshot"] = compiled.snapshot()
    current["prompt_snapshot"]["domain_profile"] = "ad"
    return current
