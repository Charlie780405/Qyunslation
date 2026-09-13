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
