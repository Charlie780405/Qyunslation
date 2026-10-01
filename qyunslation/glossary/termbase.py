# SPDX-License-Identifier: MPL-2.0
"""PLAN-058：租户/项目作用域术语加载和译前解析。"""
from __future__ import annotations

from hashlib import sha256

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from qyunslation.glossary.resolver import TermMatch, TermRecord, TermResolver, build_term_index
from qyunslation.glossary.governance import normalize_lang
from qyunslation.persist.models import Concept, ConceptTerm

FORM_LAYERS = frozenset({"form", "regulatory-form-fields"})
REGULATORY_PROFILES = frozenset({"监管申报材料"})


def _preferred_target(terms: list[ConceptTerm], lang: str) -> str | None:
    preferred = [
        t.text.strip()
        for t in terms
        if normalize_lang(t.lang) == normalize_lang(lang) and t.role == "preferred"
    ]
    return preferred[0] if preferred else None


def _profile_allowed(concept: Concept, document_profile: str | None) -> bool:
    allowed = concept.applies_to_profiles
    if not allowed:
        return True
    profile = (document_profile or "").strip()
    if not profile:
        return True
    return profile in {str(item).strip() for item in allowed if str(item).strip()}


def _layer_allowed(layer: str, document_profile: str | None) -> bool:
    normalized_layer = (layer or "").strip().casefold()
    if normalized_layer in FORM_LAYERS:
        profile = (document_profile or "").strip()
        return profile in REGULATORY_PROFILES
    return True


def list_runtime_terms(
    session: Session,
    *,
    tenant_id: str,
    project_id: str | None,
    src_lang: str = "en",
    tgt_lang: str = "zh",
    document_profile: str | None = None,
) -> list[TermRecord]:
    """Load only approved terms visible to this tenant/project."""
    src_lang = normalize_lang(src_lang) or "en"
    tgt_lang = normalize_lang(tgt_lang) or "zh"
    stmt = (
        select(Concept)
        .where(Concept.status == "curated")
        .where(or_(Concept.tenant_id.is_(None), Concept.tenant_id == tenant_id))
        .where(or_(Concept.project_id.is_(None), Concept.project_id == project_id))
        .options(selectinload(Concept.terms), selectinload(Concept.forbiddens))
    )
    concepts = list(session.scalars(stmt).unique().all())
    records: dict[tuple[str, str, str], TermRecord] = {}
    for concept in concepts:
        if not _profile_allowed(concept, document_profile):
            continue
        if not _layer_allowed(concept.layer, document_profile):
            continue
        target = _preferred_target(concept.terms, tgt_lang)
        if not target and concept.do_not_translate:
            target = _preferred_target(concept.terms, src_lang)
        if not target:
            continue
        forbidden = tuple(
            f.text.strip()
            for f in concept.forbiddens
            if f.text.strip() and (not f.lang or normalize_lang(f.lang) == tgt_lang)
        )
        source_terms = [
            t for t in concept.terms if normalize_lang(t.lang) == src_lang
        ]
        for term in source_terms:
            source = term.text.strip()
            if not source:
                continue
            record = TermRecord(
                concept_id=concept.id,
                source_term=source,
                target_term=target,
                layer=concept.layer,
                src_lang=src_lang,
                tgt_lang=tgt_lang,
                role=term.role,
                term_type=concept.term_type,
                do_not_translate=concept.do_not_translate,
                forbidden_targets=forbidden,
            )
            key = (record.normalized_source, src_lang.casefold(), tgt_lang.casefold())
            previous = records.get(key)
            if previous is None or (record.priority, record.role == "preferred") > (
                previous.priority,
                previous.role == "preferred",
            ):
                records[key] = record
    return sorted(records.values(), key=lambda record: record.normalized_source)


def resolve_runtime_terms(
    session: Session,
    *,
    tenant_id: str,
    project_id: str | None,
    text: str,
    src_lang: str = "en",
    tgt_lang: str = "zh",
    document_profile: str | None = None,
) -> list[TermMatch]:
    records = list_runtime_terms(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        src_lang=src_lang,
        tgt_lang=tgt_lang,
        document_profile=document_profile,
    )
    return TermResolver(build_term_index(records)).resolve(text)


def runtime_termbase_version(
    session: Session,
    *,
    tenant_id: str,
    project_id: str | None,
) -> str:
    """Return a stable scope/version token for translation and resolution caches."""
    stmt = (
        select(Concept.id, Concept.version, Concept.updated_at)
        .where(Concept.status == "curated")
        .where(or_(Concept.tenant_id.is_(None), Concept.tenant_id == tenant_id))
        .where(or_(Concept.project_id.is_(None), Concept.project_id == project_id))
        .order_by(Concept.id)
    )
    parts = [
        f"{concept_id}:{version}:{updated_at.isoformat() if updated_at else ''}"
        for concept_id, version, updated_at in session.execute(stmt)
    ]
    digest = sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"058-{digest[:24]}"


def match_to_dict(match: TermMatch) -> dict:
    """Serialize a resolver result, including the fields needed by the policy pack."""
    return {
        "concept_id": match.concept_id,
        "source_term": match.source_term,
        "preferred_target": match.target_term,
        "target_term": match.target_term,
        "match_type": match.match_type,
        "term_type": match.term_type,
        "do_not_translate": match.do_not_translate,
        "forbidden_targets": list(match.forbidden_targets),
        "scope": match.layer,
        "confidence": match.confidence,
        "source_locations": [{"start": match.start, "end": match.end}],
        "matched_text": match.matched_text or match.source_term,
        "hard_constraint": match.match_type in {"exact", "alias"},
    }


def term_policy(matches: list[TermMatch]) -> dict[str, str]:
    """Return a legacy glossary dictionary for existing translators."""
    policy: dict[str, str] = {}
    for match in matches:
        if match.match_type == "exact" and match.source_term not in policy:
            policy[match.source_term] = match.target_term
    return policy
