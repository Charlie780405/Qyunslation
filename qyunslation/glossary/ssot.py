# SPDX-License-Identifier: MPL-2.0
"""PLAN-034d0：术语单一事实源 — service 层挂字典，不写全表 custom_prompt。"""
from __future__ import annotations

import logging
from typing import Any

from qyunslation.extensions.glossary_db import load_glossary
from qyunslation.glossary.glossary import _normalize_key

logger = logging.getLogger(__name__)


def _normalize_dict(d: dict[str, str] | None) -> dict[str, str]:
    if not d:
        return {}
    out: dict[str, str] = {}
    for src, dst in d.items():
        key = _normalize_key(str(src))
        if not key or dst is None or str(dst).strip() == "":
            continue
        # 后写覆盖（用户上传优先）
        out[key] = str(dst)
    return out


def merge_ssot_glossary(
    user_glossary: dict[str, str] | None = None,
) -> tuple[dict[str, str], int, int]:
    """返回 (merged, ssot_count, user_override_count)。

    底层垫 SSOT（四层 + json）；用户键规范化后覆盖。
    """
    ssot = _normalize_dict(load_glossary())
    user = _normalize_dict(user_glossary)
    merged = dict(ssot)
    override = 0
    for k, v in user.items():
        if k in merged and merged[k] != v:
            override += 1
        elif k not in merged:
            override += 1
        merged[k] = v
    return merged, len(ssot), override


def apply_ssot_to_payload(payload: Any) -> dict[str, str]:
    """就地写入 payload.glossary_dict；绝不把全表写入 custom_prompt。"""
    existing = getattr(payload, "glossary_dict", None)
    merged, ssot_n, override_n = merge_ssot_glossary(
        existing if isinstance(existing, dict) else None
    )
    payload.glossary_dict = merged or None
    logger.info(
        "glossary_ssot_injected count=%s user_override=%s custom_prompt_untouched=1",
        ssot_n,
        override_n,
    )
    print(
        f"[glossary_ssot] injected count={ssot_n} user_override={override_n} "
        f"(custom_prompt not filled with full table)"
    )
    return merged


def apply_term_policy_to_payload(payload: Any, policy: dict | None) -> dict[str, str]:
    """Inject only policy-approved hard terms into every legacy workflow.

    Existing workflow adapters consume ``payload.glossary_dict``.  Keeping the
    adapter boundary here lets PDF/DOCX/PPTX/image and text paths share the
    same project-scoped policy without teaching each file workflow about the
    database.  Semantic suggestions remain in the policy for review but are
    deliberately not injected as hard glossary entries.
    """
    from qyunslation.glossary.term_policy import policy_to_glossary

    hard = policy_to_glossary(policy)
    existing = getattr(payload, "glossary_dict", None)
    merged: dict[str, str] = {}
    if isinstance(existing, dict):
        hard_keys = {_normalize_key(source) for source in hard}
        for source, target in existing.items():
            key = _normalize_key(str(source))
            if key and key not in hard_keys and target is not None and str(target).strip():
                merged[str(source)] = str(target)
    merged.update(hard)
    payload.glossary_dict = merged or None
    payload.termbase_policy = policy
    payload.termbase_version = policy.get("termbase_version") if policy else None
    logger.info(
        "termbase_policy_injected hard_terms=%s semantic_suggestions=%s version=%s",
        len(hard),
        sum(1 for term in (policy or {}).get("terms", []) if not term.get("hard_constraint")),
        payload.termbase_version,
    )
    return merged
