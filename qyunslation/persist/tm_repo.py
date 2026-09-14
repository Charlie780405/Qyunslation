# SPDX-License-Identifier: MPL-2.0
"""PLAN-034e / PLAN-055：tm_unit 仓库（批准门禁 + 租户作用域 + 语义建议）。"""
from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from qyunslation.persist.models import TmUnit, TmUnitEmbedding
from qyunslation.tm.match import exact_lookup, fuzzy_suggest
from qyunslation.tm.normalize import normalize_source, placeholder_signature

logger = logging.getLogger(__name__)

FUZZY_CANDIDATE_CAP = 2000
DEFAULT_SEMANTIC_THRESHOLD = 0.88


class ApprovalRequiredError(ValueError):
    """正式 TM 入库必须显式批准。"""


def _semantic_threshold() -> float:
    raw = (os.environ.get("QYUNSLATION_TM_SEMANTIC_THRESHOLD") or "").strip()
    if not raw:
        return DEFAULT_SEMANTIC_THRESHOLD
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_SEMANTIC_THRESHOLD


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        xf = float(x)
        yf = float(y)
        dot += xf * yf
        na += xf * xf
        nb += yf * yf
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def tm_unit_to_dict(unit: TmUnit) -> dict[str, Any]:
    return {
        "id": unit.id,
        "tenant_id": unit.tenant_id,
        "project_id": unit.project_id,
        "src_lang": unit.src_lang,
        "tgt_lang": unit.tgt_lang,
        "source_text": unit.source_text,
        "target_text": unit.target_text,
        "source_norm": unit.source_norm,
        "placeholder_sig": unit.placeholder_sig,
        "approved": unit.approved,
        "approved_by": unit.approved_by,
        "approved_at": unit.approved_at.isoformat() if unit.approved_at else None,
        "version": unit.version,
        "created_at": unit.created_at.isoformat(),
        "updated_at": unit.updated_at.isoformat(),
    }


def upsert_unit_embedding(session: Session, unit: TmUnit) -> TmUnitEmbedding | None:
    """同步写入向量；失败返回 None，不抛（不挡批准）。"""
    try:
        from qyunslation.embed import client as embed_client

        vectors = embed_client.embed_texts([unit.source_text])
        if not vectors:
            return None
        vec = vectors[0]
        model = embed_client._model()
        dim = len(vec)
    except Exception as exc:  # noqa: BLE001 — 批准路径必须吞掉
        logger.warning("tm embed failed unit=%s: %s", getattr(unit, "id", "?"), exc)
        return None
    now = datetime.now(timezone.utc)
    row = session.get(TmUnitEmbedding, unit.id)
    if row is None:
        row = TmUnitEmbedding(
            unit_id=unit.id,
            dim=dim,
            model=model,
            vector=vec,
            created_at=now,
        )
        session.add(row)
    else:
        row.dim = dim
        row.model = model
        row.vector = vec
        row.created_at = now
    session.flush()
    return row


def create_approved_unit(
    session: Session,
    *,
    tenant_id: str,
    source_text: str,
    target_text: str,
    approved: bool,
    approved_by: str | None = None,
    project_id: str | None = None,
    src_lang: str = "en",
    tgt_lang: str = "zh",
) -> TmUnit:
    if not approved:
        raise ApprovalRequiredError("approved=true required to enter formal TM")
    sn = normalize_source(source_text)
    sig = placeholder_signature(source_text)
    stmt = select(TmUnit).where(
        TmUnit.tenant_id == tenant_id,
        TmUnit.src_lang == src_lang,
        TmUnit.tgt_lang == tgt_lang,
        TmUnit.source_norm == sn,
        TmUnit.placeholder_sig == sig,
        TmUnit.approved.is_(True),
    )
    if project_id is None:
        stmt = stmt.where(TmUnit.project_id.is_(None))
    else:
        stmt = stmt.where(TmUnit.project_id == project_id)
    existing = session.scalar(stmt)
    now = datetime.now(timezone.utc)
    if existing is not None:
        existing.source_text = source_text
        existing.target_text = target_text
        existing.version = int(existing.version or 1) + 1
        existing.approved_by = approved_by
        existing.approved_at = now
        existing.updated_at = now
        session.flush()
        upsert_unit_embedding(session, existing)
        return existing
    unit = TmUnit(
        tenant_id=tenant_id,
        project_id=project_id,
        src_lang=src_lang,
        tgt_lang=tgt_lang,
        source_text=source_text,
        target_text=target_text,
        source_norm=sn,
        placeholder_sig=sig,
        approved=True,
        approved_by=approved_by,
        approved_at=now,
        version=1,
    )
    session.add(unit)
    session.flush()
    upsert_unit_embedding(session, unit)
    return unit


def stage_import_unit(
    session: Session,
    *,
    tenant_id: str,
    source_text: str,
    target_text: str,
    project_id: str | None = None,
    src_lang: str = "en",
    tgt_lang: str = "zh",
) -> TmUnit:
    """TMX 导入：默认 ``approved=false``，不入正式匹配池。"""
    unit = TmUnit(
        tenant_id=tenant_id,
        project_id=project_id,
        src_lang=src_lang,
        tgt_lang=tgt_lang,
        source_text=source_text,
        target_text=target_text,
        source_norm=normalize_source(source_text),
        placeholder_sig=placeholder_signature(source_text),
        approved=False,
        approved_by=None,
        approved_at=None,
        version=1,
    )
    session.add(unit)
    session.flush()
    return unit


def list_approved_units(
    session: Session,
    *,
    tenant_id: str,
    src_lang: str | None = None,
    tgt_lang: str | None = None,
    project_id: str | None = None,
    limit: int | None = None,
) -> list[TmUnit]:
    stmt = select(TmUnit).where(
        TmUnit.tenant_id == tenant_id,
        TmUnit.approved.is_(True),
    )
    if src_lang:
        stmt = stmt.where(TmUnit.src_lang == src_lang)
    if tgt_lang:
        stmt = stmt.where(TmUnit.tgt_lang == tgt_lang)
    if project_id is not None:
        stmt = stmt.where(
            (TmUnit.project_id == project_id) | (TmUnit.project_id.is_(None))
        )
    if limit is not None:
        stmt = stmt.order_by(TmUnit.updated_at.desc()).limit(limit)
    return list(session.scalars(stmt).all())


def lookup(
    session: Session,
    *,
    tenant_id: str,
    source_text: str,
    src_lang: str = "en",
    tgt_lang: str = "zh",
    project_id: str | None = None,
    fuzzy_threshold: float = 0.85,
    fuzzy_limit: int = 5,
    semantic_limit: int = 5,
    semantic_threshold: float | None = None,
) -> dict[str, Any]:
    qn = normalize_source(source_text)
    qs = placeholder_signature(source_text)

    # 精确命中走 ix_tm_unit_lookup 索引，不把全租户 TM 拉进内存
    exact_stmt = select(TmUnit).where(
        TmUnit.tenant_id == tenant_id,
        TmUnit.approved.is_(True),
        TmUnit.src_lang == src_lang,
        TmUnit.tgt_lang == tgt_lang,
        TmUnit.source_norm == qn,
        TmUnit.placeholder_sig == qs,
    )
    if project_id is not None:
        exact_stmt = exact_stmt.where(
            (TmUnit.project_id == project_id) | (TmUnit.project_id.is_(None))
        )
    exact_row = session.scalars(exact_stmt.limit(1)).first()
    hit = (
        exact_lookup(source_text, [exact_row], query_norm=qn, query_sig=qs)
        if exact_row is not None
        else None
    )
    if hit is not None:
        return {
            "reuse": True,
            "match": {
                "unit_id": hit.unit_id,
                "source_text": hit.source_text,
                "target_text": hit.target_text,
                "score": hit.score,
                "source_norm": hit.source_norm,
                "placeholder_sig": hit.placeholder_sig,
            },
            "suggestions": [],
            "semantic_suggestions": [],
            "query_norm": qn,
            "placeholder_sig": qs,
        }
    # 模糊必须逐条比对，故只取最近 FUZZY_CANDIDATE_CAP 条候选
    candidates = list_approved_units(
        session,
        tenant_id=tenant_id,
        src_lang=src_lang,
        tgt_lang=tgt_lang,
        project_id=project_id,
        limit=FUZZY_CANDIDATE_CAP,
    )
    semantic_suggestions = _semantic_suggestions(
        session,
        source_text=source_text,
        candidates=candidates,
        limit=semantic_limit,
        threshold=semantic_threshold
        if semantic_threshold is not None
        else _semantic_threshold(),
    )
    suggestions = fuzzy_suggest(
        source_text,
        candidates,
        threshold=fuzzy_threshold,
        limit=fuzzy_limit,
        query_norm=qn,
    )
    return {
        "reuse": False,
        "match": None,
        "suggestions": [
            {
                "unit_id": s.unit_id,
                "source_text": s.source_text,
                "target_text": s.target_text,
                "score": s.score,
                "source_norm": s.source_norm,
                "placeholder_sig": s.placeholder_sig,
            }
            for s in suggestions
        ],
        "semantic_suggestions": semantic_suggestions,
        "query_norm": qn,
        "placeholder_sig": qs,
    }


def _semantic_suggestions(
    session: Session,
    *,
    source_text: str,
    candidates: list[TmUnit],
    limit: int,
    threshold: float,
) -> list[dict[str, Any]]:
    if limit <= 0 or not candidates:
        return []
    try:
        from qyunslation.embed.client import embed_texts

        qvecs = embed_texts([source_text])
        if not qvecs:
            return []
        qvec = qvecs[0]
    except Exception as exc:  # noqa: BLE001
        logger.warning("tm semantic query embed failed: %s", exc)
        return []

    ids = [u.id for u in candidates]
    emb_rows = list(
        session.scalars(
            select(TmUnitEmbedding).where(TmUnitEmbedding.unit_id.in_(ids))
        ).all()
    )
    by_id = {e.unit_id: e for e in emb_rows}
    scored: list[tuple[float, TmUnit]] = []
    for unit in candidates:
        emb = by_id.get(unit.id)
        if emb is None or not isinstance(emb.vector, list):
            continue
        score = cosine_similarity(qvec, list(emb.vector))
        if score >= threshold:
            scored.append((score, unit))
    scored.sort(key=lambda x: x[0], reverse=True)
    out: list[dict[str, Any]] = []
    for score, unit in scored[:limit]:
        out.append(
            {
                "unit_id": unit.id,
                "source_text": unit.source_text,
                "target_text": unit.target_text,
                "score": round(float(score), 6),
                "source_norm": unit.source_norm,
                "placeholder_sig": unit.placeholder_sig,
                "kind": "semantic",
            }
        )
    return out
