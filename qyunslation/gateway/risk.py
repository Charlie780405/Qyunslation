# SPDX-License-Identifier: MPL-2.0
"""PLAN-034f：文档领域 + 对象角色 → 风险分级（纯函数，无 LLM）。"""
from __future__ import annotations

from typing import Any

# 角色别名归一
_ROLE_MAP = {
    "body": "body",
    "paragraph": "body",
    "text": "body",
    "table": "table",
    "table_cell": "table",
    "cell": "table",
    "caption": "caption",
    "figure_caption": "caption",
    "figcaption": "caption",
    "figure": "figure",
    "image": "figure",
    "references": "references",
    "reference": "references",
    "bibliography": "references",
    "dose": "dose",
    "dosage": "dose",
}


def normalize_role(role: str | None) -> str:
    key = (role or "body").strip().lower()
    return _ROLE_MAP.get(key, key or "body")


def grade_risk(domain: str | None, role: str | None) -> dict[str, Any]:
    """返回 ``{level, policy, reason}``。

    - 参考文献 → PRESERVE / low
    - 表 / 剂量 → critical
    - 图注 → medium
    - 正文默认 medium
    """
    r = normalize_role(role)
    d = (domain or "").strip().lower()

    if r in {"references", "bibliography"}:
        return {
            "level": "low",
            "policy": "PRESERVE",
            "reason": "references must not enter LLM",
            "role": r,
            "domain": d,
        }
    if r in {"table", "dose"} or "dose" in d or "csr" in d and r == "table":
        return {
            "level": "critical",
            "policy": "TRANSLATE",
            "reason": "table/dose fidelity",
            "role": r,
            "domain": d,
        }
    if r in {"caption", "figure"}:
        return {
            "level": "medium",
            "policy": "TRANSLATE",
            "reason": "figure/caption",
            "role": r,
            "domain": d,
        }
    if d in {"ctd", "ib", "protocol"} and r == "body":
        return {
            "level": "high",
            "policy": "TRANSLATE",
            "reason": "regulatory body text",
            "role": r,
            "domain": d,
        }
    return {
        "level": "medium",
        "policy": "TRANSLATE",
        "reason": "default body",
        "role": r,
        "domain": d,
    }
