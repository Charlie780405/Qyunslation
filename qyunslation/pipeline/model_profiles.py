# SPDX-License-Identifier: MPL-2.0
"""PLAN-071g：受控模型配置与资料等级矩阵。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


CLASSIFICATIONS = ("confidential", "internal", "public")


@dataclass(frozen=True)
class ModelProfile:
    profile_id: str
    role: str  # translator | term_suggester
    provider: str
    model_id: str
    label: str
    experimental: bool = False


PROFILES: dict[str, ModelProfile] = {
    "internal-qwen-quality": ModelProfile(
        profile_id="internal-qwen-quality",
        role="translator",
        provider="ollama",
        model_id=os.environ.get("DOCUTRANSLATE_MODEL_ID")
        or os.environ.get("QYUNSLATION_MODEL_ID")
        or "qwen3.6:35b-a3b",
        label="内网 Qwen 质量档",
    ),
    "public-deepseek-flash": ModelProfile(
        profile_id="public-deepseek-flash",
        role="translator",
        provider="deepseek",
        model_id="deepseek-flash",
        label="DeepSeek Flash（公开资料）",
        experimental=True,
    ),
    # PLAN-078a / D1: structured term extraction on the Taizhou in-house Qwen. Nothing
    # leaves the network, so it is the only term model confidential material may use.
    "term-internal-qwen": ModelProfile(
        profile_id="term-internal-qwen",
        role="term_suggester",
        provider="ollama",
        model_id=os.environ.get("QYUNSLATION_TERM_MODEL_ID")
        or os.environ.get("DOCUTRANSLATE_MODEL_ID")
        or os.environ.get("QYUNSLATION_MODEL_ID")
        or "qwen3.6:35b-a3b",
        label="内网 Qwen（术语抽取，无外发）",
    ),
    "term-deepseek-flash": ModelProfile(
        profile_id="term-deepseek-flash",
        role="term_suggester",
        provider="deepseek",
        model_id="deepseek-flash",
        label="DeepSeek Flash（脱敏术语）",
        experimental=True,
    ),
}


def deepseek_configured() -> bool:
    return bool(
        (os.environ.get("QYUNSLATION_DEEPSEEK_API_KEY") or "").strip()
        or (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    )


def allowed_profiles(classification: str) -> list[ModelProfile]:
    c = (classification or "internal").strip().casefold()
    if c not in CLASSIFICATIONS:
        c = "internal"
    if c == "confidential":
        return [PROFILES["internal-qwen-quality"], PROFILES["term-internal-qwen"]]
    if c == "internal":
        return [
            PROFILES["internal-qwen-quality"],
            PROFILES["term-internal-qwen"],
            PROFILES["term-deepseek-flash"],
        ]
    return [
        PROFILES["internal-qwen-quality"],
        PROFILES["public-deepseek-flash"],
        PROFILES["term-internal-qwen"],
        PROFILES["term-deepseek-flash"],
    ]


def default_term_profile_id(classification: str) -> str:
    """Term model used when the request names none.

    Confidential material is pinned to the in-house model. Other levels keep the
    DeepSeek helper when it is configured (unchanged behaviour) and otherwise use the
    in-house model instead of silently running with no term model at all.
    """
    c = (classification or "internal").strip().casefold()
    if c != "confidential" and deepseek_configured():
        return "term-deepseek-flash"
    return "term-internal-qwen"


def validate_selection(
    *,
    classification: str,
    model_profile_id: str | None,
    term_profile_id: str | None = None,
) -> tuple[str, str | None, str | None]:
    c = (classification or "internal").strip().casefold()
    if c not in CLASSIFICATIONS:
        raise ValueError("invalid document_classification")
    allowed = {p.profile_id: p for p in allowed_profiles(c)}
    translator_id = model_profile_id or "internal-qwen-quality"
    if translator_id not in allowed or allowed[translator_id].role != "translator":
        # internal allows only qwen as translator
        if translator_id != "internal-qwen-quality":
            raise ValueError("model_profile_id not allowed for classification")
    if c == "confidential" and translator_id != "internal-qwen-quality":
        raise ValueError("confidential forbids external translator")
    if c == "internal" and translator_id != "internal-qwen-quality":
        raise ValueError("internal forbids external full-document model")
    term_id = term_profile_id
    if term_id:
        if term_id not in allowed or allowed[term_id].role != "term_suggester":
            raise ValueError("term model not allowed for classification")
        if c == "confidential" and allowed[term_id].provider not in {"ollama", "internal"}:
            raise ValueError("confidential forbids external term model")
        if allowed[term_id].provider == "deepseek" and not deepseek_configured():
            raise ValueError("deepseek not configured")
    if allowed[translator_id].provider == "deepseek" and not deepseek_configured():
        raise ValueError("deepseek not configured")
    return c, translator_id, term_id


def profiles_payload(classification: str) -> list[dict[str, Any]]:
    out = []
    for profile in allowed_profiles(classification):
        out.append(
            {
                "profile_id": profile.profile_id,
                "role": profile.role,
                "provider": profile.provider,
                "model_id": profile.model_id,
                "label": profile.label,
                "experimental": profile.experimental,
                "configured": True
                if profile.provider != "deepseek"
                else deepseek_configured(),
            }
        )
    return out
