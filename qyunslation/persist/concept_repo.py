# SPDX-License-Identifier: MPL-2.0
"""PLAN-034d：Concept 仓储与禁用译法检测。"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from qyunslation.glossary.governance import (
    GlossaryEntry,
    LAYER_PRIORITY,
    normalize_lang,
    normalize_source,
)
from qyunslation.persist.models import Concept, ConceptForbidden, ConceptTerm

VALID_CONCEPT_STATUS = frozenset({"curated", "staging", "rejected"})
VALID_TERM_ROLES = frozenset({"preferred", "synonym", "abbreviation"})
# 词库页一次取全：旧上限 200 会让超出的术语完全看不到。
LIST_LIMIT_DEFAULT = 2000
LIST_LIMIT_MAX = 5000


def make_import_key(*, source: str, layer: str, src_lng: str, tgt_lng: str) -> str:
    return "|".join(
        [
            normalize_source(source),
            (layer or "clinical").casefold(),
            normalize_lang(src_lng) or "en",
            normalize_lang(tgt_lng) or "zh",
        ]
    )


def list_concepts(
    session: Session,
    *,
    status: str | None = None,
    tenant_id: str | None = None,
    limit: int = LIST_LIMIT_DEFAULT,
) -> list[Concept]:
    stmt = select(Concept).options(
        selectinload(Concept.terms),
        selectinload(Concept.forbiddens),
    )
    if tenant_id:
        # 全局术语（无租户）：已批准的可见，被驳回的也要可见，否则驳回后无处恢复。
        stmt = stmt.where(
            (Concept.tenant_id == tenant_id)
            | ((Concept.tenant_id.is_(None)) & (Concept.status.in_(("curated", "rejected"))))
        )
    if status:
        stmt = stmt.where(Concept.status == status)
    stmt = stmt.order_by(Concept.created_at.desc()).limit(limit)
    return list(session.scalars(stmt))


def get_concept(session: Session, concept_id: str) -> Concept | None:
    return session.scalar(
        select(Concept)
        .where(Concept.id == concept_id)
        .options(selectinload(Concept.terms), selectinload(Concept.forbiddens))
    )


def create_staging_concept(
    session: Session,
    *,
    domain: str = "",
    layer: str = "session",
    preferred_source: str,
    preferred_target: str,
    src_lng: str = "en",
    tgt_lng: str = "zh",
    evidence: str | None = None,
    do_not_translate: bool = False,
    forbidden: list[tuple[str, str]] | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    term_type: str = "general",
) -> Concept:
    """API/LLM 路径：强制 staging。"""
    concept = Concept(
        domain=domain or "",
        status="staging",
        version=1,
        evidence=evidence,
        do_not_translate=do_not_translate,
        layer=layer or "session",
        tenant_id=tenant_id,
        project_id=project_id,
        term_type=term_type or "general",
        import_key=None,
    )
    session.add(concept)
    session.flush()
    session.add(
        ConceptTerm(
            concept_id=concept.id,
            lang=normalize_lang(src_lng) or "en",
            text=preferred_source.strip(),
            normalized_text=normalize_source(preferred_source),
            role="preferred",
        )
    )
    session.add(
        ConceptTerm(
            concept_id=concept.id,
            lang=normalize_lang(tgt_lng) or "zh",
            text=preferred_target.strip(),
            normalized_text=normalize_source(preferred_target),
            role="preferred",
        )
    )
    for lang, text in forbidden or []:
        t = (text or "").strip()
        if not t:
            continue
        session.add(
            ConceptForbidden(
                concept_id=concept.id,
                lang=normalize_lang(lang) or "",
                text=t,
            )
        )
    session.flush()
    return get_concept(session, concept.id) or concept


def upsert_curated_from_entry(session: Session, entry: GlossaryEntry) -> Concept:
    """幂等导入 curated CSV 行。"""
    key = make_import_key(
        source=entry.source,
        layer=entry.layer,
        src_lng=entry.src_lng,
        tgt_lng=entry.tgt_lng,
    )
    existing = session.scalar(
        select(Concept)
        .where(Concept.import_key == key)
        .options(selectinload(Concept.terms))
    )
    src_lang = normalize_lang(entry.src_lng) or "en"
    tgt_lang = normalize_lang(entry.tgt_lng) or ("en" if src_lang == "zh" else "zh")
    identity = (
        normalize_source(entry.source) == normalize_source(entry.target)
        and src_lang == tgt_lang
    )

    def _attach_terms(concept_id: str) -> None:
        session.add(
            ConceptTerm(
                concept_id=concept_id,
                lang=src_lang,
                text=entry.source,
                normalized_text=normalize_source(entry.source),
                role="preferred",
            )
        )
        if not identity:
            session.add(
                ConceptTerm(
                    concept_id=concept_id,
                    lang=tgt_lang,
                    text=entry.target,
                    normalized_text=normalize_source(entry.target),
                    role="preferred",
                )
            )

    if existing is not None:
        existing.domain = entry.domain or existing.domain
        existing.status = "curated"
        existing.layer = entry.layer
        existing.evidence = entry.notes or existing.evidence
        existing.do_not_translate = identity
        # 幂等：已有 preferred 且文本一致则不重写，避免 SQLite UNIQUE 冲突
        pref = {(t.lang, t.text) for t in existing.terms if t.role == "preferred"}
        want = {(src_lang, entry.source)}
        if not identity:
            want.add((tgt_lang, entry.target))
        if pref != want:
            for term in list(existing.terms):
                session.delete(term)
            session.flush()
            _attach_terms(existing.id)
            session.flush()
        return existing

    concept = Concept(
        domain=entry.domain or "",
        status="curated",
        version=1,
        evidence=entry.notes or None,
        do_not_translate=identity,
        layer=entry.layer,
        tenant_id=None,
        project_id=None,
        term_type="general",
        import_key=key,
    )
    session.add(concept)
    session.flush()
    _attach_terms(concept.id)
    session.flush()
    return concept


def curated_concepts(session: Session) -> list[Concept]:
    return list(
        session.scalars(
            select(Concept)
            .where(Concept.status == "curated")
            .options(selectinload(Concept.terms), selectinload(Concept.forbiddens))
        )
    )


def count_by_status(session: Session, status: str) -> int:
    from sqlalchemy import func

    return int(
        session.scalar(select(func.count()).select_from(Concept).where(Concept.status == status))
        or 0
    )


def list_forbidden_texts(session: Session, *, curated_only: bool = True) -> list[str]:
    stmt = select(ConceptForbidden.text).join(Concept)
    if curated_only:
        stmt = stmt.where(Concept.status == "curated")
    return [t for t in session.scalars(stmt) if t]


def detect_forbidden(text: str, forbidden_hits: list[str] | None) -> bool:
    """纯函数：译文命中任一禁用串则 True。"""
    hay = (text or "").casefold()
    if not hay or not forbidden_hits:
        return False
    for hit in forbidden_hits:
        needle = (hit or "").strip().casefold()
        if needle and needle in hay:
            return True
    return False


def set_concept_status(concept: Concept, status: str, *, actor: str, note: str = "") -> bool:
    """改状态（curated / staging / rejected）；无变化返回 False。留痕写进 evidence 并升版本。"""
    if status not in VALID_CONCEPT_STATUS:
        raise ValueError(f"invalid concept status: {status}")
    if concept.status == status:
        return False
    previous = concept.status
    concept.status = status
    concept.version = (concept.version or 1) + 1
    concept.evidence = f"{concept.evidence or ''};status:{previous}->{status};by:{actor}" + (
        f";note:{note}" if note else ""
    )
    return True


_REJECT_TRAIL = re.compile(r"status:(curated|staging)->rejected")


def previous_status(concept: Concept) -> str:
    """被驳回前的状态（取留痕里最近一次）；查不到回到待审核，绝不自动变成已批准。"""
    matches = _REJECT_TRAIL.findall(concept.evidence or "")
    return matches[-1] if matches else "staging"


def resolve_requested_status(concept: Concept, requested: str) -> str:
    """``restore`` 还原到驳回前；已不是驳回状态则保持不动。"""
    if requested != "restore":
        return requested
    return previous_status(concept) if concept.status == "rejected" else concept.status


def set_preferred_target(
    session: Session, concept: Concept, *, text: str, tgt_lng: str = "zh"
) -> None:
    """补充/更新译名：替换该语言的优选译名，并取消“保持原文”标记。"""
    clean = (text or "").strip()
    if not clean:
        raise ValueError("target text is empty")
    lang = normalize_lang(tgt_lng) or "zh"
    for term in list(concept.terms):
        if term.role == "preferred" and term.lang == lang:
            session.delete(term)
    session.flush()
    session.add(
        ConceptTerm(
            concept_id=concept.id,
            lang=lang,
            text=clean,
            normalized_text=normalize_source(clean),
            role="preferred",
        )
    )
    concept.do_not_translate = False
    concept.version = (concept.version or 1) + 1
    session.flush()
    session.refresh(concept)


def concept_to_dict(concept: Concept) -> dict:
    from qyunslation.glossary.term_compliance import assess_concept, preferred_pair

    source, target = preferred_pair(list(concept.terms))
    if target:
        target_state = "translated"
    elif concept.do_not_translate:
        target_state = "keep_source"
    else:
        target_state = "missing"
    return {
        "target_state": target_state,
        "compliance": assess_concept(
            source,
            target,
            do_not_translate=bool(concept.do_not_translate),
            evidence=concept.evidence,
            term_type=concept.term_type,
        ),
        **_concept_core(concept),
    }


def _concept_core(concept: Concept) -> dict:
    return {
        "id": concept.id,
        "domain": concept.domain,
        "status": concept.status,
        "version": concept.version,
        "license": concept.license,
        "evidence": concept.evidence,
        "do_not_translate": concept.do_not_translate,
        "layer": concept.layer,
        "project_id": concept.project_id,
        "term_type": concept.term_type,
        "definition": concept.definition,
        "authority": concept.authority,
        "tenant_id": concept.tenant_id,
        "terms": [
            {
                "lang": t.lang,
                "text": t.text,
                "normalized_text": t.normalized_text,
                "role": t.role,
            }
            for t in concept.terms
        ],
        "forbiddens": [
            {"lang": f.lang, "text": f.text} for f in concept.forbiddens
        ],
        "created_at": concept.created_at.isoformat() if concept.created_at else None,
    }


def layer_sort_key(layer: str) -> int:
    return LAYER_PRIORITY.get((layer or "").casefold(), 0)
