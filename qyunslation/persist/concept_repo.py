# SPDX-License-Identifier: MPL-2.0
"""PLAN-034d：Concept 仓储与禁用译法检测。"""
from __future__ import annotations

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
    limit: int = 200,
) -> list[Concept]:
    stmt = select(Concept).options(
        selectinload(Concept.terms),
        selectinload(Concept.forbiddens),
    )
    if tenant_id:
        stmt = stmt.where(
            (Concept.tenant_id == tenant_id)
            | ((Concept.tenant_id.is_(None)) & (Concept.status == "curated"))
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
        import_key=None,
    )
    session.add(concept)
    session.flush()
    session.add(
        ConceptTerm(
            concept_id=concept.id,
            lang=normalize_lang(src_lng) or "en",
            text=preferred_source.strip(),
            role="preferred",
        )
    )
    session.add(
        ConceptTerm(
            concept_id=concept.id,
            lang=normalize_lang(tgt_lng) or "zh",
            text=preferred_target.strip(),
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
                role="preferred",
            )
        )
        if not identity:
            session.add(
                ConceptTerm(
                    concept_id=concept_id,
                    lang=tgt_lang,
                    text=entry.target,
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


def concept_to_dict(concept: Concept) -> dict:
    return {
        "id": concept.id,
        "domain": concept.domain,
        "status": concept.status,
        "version": concept.version,
        "license": concept.license,
        "evidence": concept.evidence,
        "do_not_translate": concept.do_not_translate,
        "layer": concept.layer,
        "tenant_id": concept.tenant_id,
        "terms": [
            {"lang": t.lang, "text": t.text, "role": t.role} for t in concept.terms
        ],
        "forbiddens": [
            {"lang": f.lang, "text": f.text} for f in concept.forbiddens
        ],
        "created_at": concept.created_at.isoformat() if concept.created_at else None,
    }


def layer_sort_key(layer: str) -> int:
    return LAYER_PRIORITY.get((layer or "").casefold(), 0)
