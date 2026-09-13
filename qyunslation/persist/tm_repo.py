# SPDX-License-Identifier: MPL-2.0
"""PLAN-034e：tm_unit 仓库（批准门禁 + 租户作用域）。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from qyunslation.persist.models import TmUnit
from qyunslation.tm.match import exact_lookup, fuzzy_suggest
from qyunslation.tm.normalize import normalize_source, placeholder_signature


class ApprovalRequiredError(ValueError):
    """正式 TM 入库必须显式批准。"""


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
) -> dict[str, Any]:
    units = list_approved_units(
        session,
        tenant_id=tenant_id,
        src_lang=src_lang,
        tgt_lang=tgt_lang,
        project_id=project_id,
    )
    qn = normalize_source(source_text)
    qs = placeholder_signature(source_text)
    hit = exact_lookup(source_text, units, query_norm=qn, query_sig=qs)
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
            "query_norm": qn,
            "placeholder_sig": qs,
        }
    suggestions = fuzzy_suggest(
        source_text,
        units,
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
        "query_norm": qn,
        "placeholder_sig": qs,
    }
