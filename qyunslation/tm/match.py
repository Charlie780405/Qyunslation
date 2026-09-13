# SPDX-License-Identifier: MPL-2.0
"""PLAN-034e：精确复用与模糊建议（stdlib difflib）。"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Sequence

from qyunslation.tm.normalize import normalize_source, placeholder_signature

DEFAULT_FUZZY_THRESHOLD = 0.85


@dataclass(frozen=True)
class TmHit:
    unit_id: str
    source_text: str
    target_text: str
    score: float
    source_norm: str
    placeholder_sig: str


def exact_lookup(
    query: str,
    units: Sequence[object],
    *,
    query_norm: str | None = None,
    query_sig: str | None = None,
) -> TmHit | None:
    """``source_norm`` 与 ``placeholder_sig`` 均相等 → 精确命中。

    ``units`` 元素需具备 ``id/source_text/target_text/source_norm/placeholder_sig``。
    """
    qn = query_norm if query_norm is not None else normalize_source(query)
    qs = query_sig if query_sig is not None else placeholder_signature(query)
    for u in units:
        if getattr(u, "source_norm", None) == qn and getattr(u, "placeholder_sig", None) == qs:
            return TmHit(
                unit_id=str(getattr(u, "id")),
                source_text=str(getattr(u, "source_text")),
                target_text=str(getattr(u, "target_text")),
                score=1.0,
                source_norm=qn,
                placeholder_sig=qs,
            )
    return None


def fuzzy_suggest(
    query: str,
    units: Sequence[object],
    *,
    threshold: float = DEFAULT_FUZZY_THRESHOLD,
    limit: int = 5,
    query_norm: str | None = None,
) -> list[TmHit]:
    """编辑距离相似度 ≥ threshold 的建议；调用方须设 ``reuse=false``。"""
    qn = query_norm if query_norm is not None else normalize_source(query)
    if not qn:
        return []
    scored: list[TmHit] = []
    for u in units:
        sn = str(getattr(u, "source_norm") or "")
        if not sn:
            continue
        # 精确已由 exact_lookup 处理；此处跳过完全相同
        if sn == qn and getattr(u, "placeholder_sig", None) == placeholder_signature(query):
            continue
        ratio = SequenceMatcher(None, qn, sn).ratio()
        if ratio >= threshold:
            scored.append(
                TmHit(
                    unit_id=str(getattr(u, "id")),
                    source_text=str(getattr(u, "source_text")),
                    target_text=str(getattr(u, "target_text")),
                    score=round(ratio, 4),
                    source_norm=sn,
                    placeholder_sig=str(getattr(u, "placeholder_sig") or ""),
                )
            )
    scored.sort(key=lambda h: (-h.score, h.unit_id))
    return scored[: max(0, limit)]
