# SPDX-License-Identifier: MPL-2.0
"""PLAN-034f：网关档位解析与 provenance 组装。"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from qyunslation.structure.model_trace import strip_endpoint

BASELINE_MODEL_ID = "qwen3.6:35b-a3b"
PROFILES_PATH = Path(__file__).with_name("profiles.yaml")
GATEWAY_PROFILE_ENV = "QYUNSLATION_GATEWAY_PROFILE"


class ProfileNotWiredError(ValueError):
    """选中档位尚未接线。"""


@lru_cache(maxsize=1)
def load_profiles() -> dict[str, Any]:
    with PROFILES_PATH.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError("profiles.yaml must be a mapping")
    return data


def clear_profiles_cache() -> None:
    load_profiles.cache_clear()


def _env_endpoint(profile_cfg: dict[str, Any]) -> str:
    for key in (
        profile_cfg.get("base_url_env"),
        profile_cfg.get("base_url_env_fallback"),
        "QYUNSLATION_BASE_URL",
        "DOCUTRANSLATE_BASE_URL",
    ):
        if not key:
            continue
        val = (os.environ.get(str(key)) or "").strip()
        if val:
            return val
    return ""


def resolve_profile(name: str | None = None) -> dict[str, Any]:
    """解析档位；未接线档位抛 ``ProfileNotWiredError``。"""
    data = load_profiles()
    profiles = data.get("profiles") or {}
    chosen = (name or os.environ.get(GATEWAY_PROFILE_ENV) or data.get("default_profile") or "quality")
    chosen = str(chosen).strip().lower()
    if chosen not in profiles:
        raise ProfileNotWiredError(f"unknown gateway profile: {chosen}")
    cfg = dict(profiles[chosen] or {})
    if not cfg.get("wired"):
        raise ProfileNotWiredError(
            f"gateway profile '{chosen}' is not wired (reserved slot)"
        )
    model_id = str(cfg.get("model_id") or "").strip()
    if not model_id:
        raise ProfileNotWiredError(f"gateway profile '{chosen}' missing model_id")
    endpoint = _env_endpoint(cfg)
    return {
        "profile": chosen,
        "provider": str(cfg.get("provider") or "qwen_ollama"),
        "model_id": model_id,
        "endpoint": endpoint,
        "endpoint_stripped": strip_endpoint(endpoint) if endpoint else "",
        "prompt_version": str(data.get("prompt_version") or "034f-v1"),
        "algorithm_version": str(data.get("algorithm_version") or "034f-qa-v1"),
        "renderer_version": str(data.get("renderer_version") or "office-sidecar"),
        "baseline_model_id": str(data.get("baseline_model_id") or BASELINE_MODEL_ID),
        "wired": True,
    }


def apply_gateway_profile(payload: Any, *, profile: str | None = None) -> dict[str, Any]:
    """就地填入 payload.model_id / base_url（已有用户值则不覆盖）。"""
    resolved = resolve_profile(profile)
    existing_model = getattr(payload, "model_id", None)
    existing_url = getattr(payload, "base_url", None)
    if not (existing_model and str(existing_model).strip()):
        payload.model_id = resolved["model_id"]
    if not (existing_url and str(existing_url).strip()) and resolved["endpoint"]:
        payload.base_url = resolved["endpoint"]
    return resolved


def build_provenance(
    *,
    profile: str | None = None,
    glossary_version: str | None = None,
    tm_version: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """组装 job.provenance；永不包含 API Key。"""
    resolved = resolve_profile(profile)
    prov: dict[str, Any] = {
        "model_id": resolved["model_id"],
        "endpoint": resolved["endpoint_stripped"],
        "prompt_version": resolved["prompt_version"],
        "glossary_version": glossary_version or "034d-curated",
        "tm_version": tm_version or "034e-tm_unit",
        "algorithm_version": resolved["algorithm_version"],
        "renderer_version": resolved["renderer_version"],
        "profile": resolved["profile"],
        "provider": resolved["provider"],
    }
    if extra:
        for k, v in extra.items():
            key = str(k).strip().lower()
            if key in {
                "api_key",
                "apikey",
                "api-key",
                "authorization",
                "password",
                "secret",
                "token",
                "access_token",
                "refresh_token",
                "bearer",
            }:
                continue
            if key not in prov:
                prov[k] = v
    if prov.get("endpoint"):
        prov["endpoint"] = strip_endpoint(str(prov["endpoint"]))
    for bad in ("api_key", "authorization", "password", "secret", "token"):
        if bad in {str(k).lower() for k in prov}:
            raise ValueError("PROVENANCE_SECRET: credentials must not be recorded")
    return prov
