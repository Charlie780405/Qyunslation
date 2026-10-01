# SPDX-License-Identifier: MPL-2.0
"""PLAN-058：译后术语候选、出现位置与人工裁决仓储。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from qyunslation.glossary.governance import normalize_lang, normalize_source
from qyunslation.glossary.term_morphology import (
    EMPTY_REJECTED_INDEX,
    RejectedIndex,
    build_rejected_index,
    has_prefix,
    morphology_stem,
)
from qyunslation.persist.models import (
    Concept,
    ConceptTerm,
    DocumentTermCandidate,
    DocumentTermOccurrence,
    Job,
    TermDecision,
)


class CandidateConflict(ValueError):
    """候选已被其他审校者更新，调用方必须重新加载后再决定。"""


VALID_DECISIONS = frozenset(
    {"approve", "reject", "merge", "do_not_translate", "submit_for_admin"}
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def candidate_to_dict(
    candidate: DocumentTermCandidate, *, include_occurrences: bool = True
) -> dict:
    """将候选序列化为 API/UI 可直接消费的稳定结构。"""
    decisions = sorted(
        candidate.decisions,
        key=lambda item: item.created_at.isoformat() if item.created_at else "",
    )
    confirmed_target = decisions[-1].target_term if decisions else None
    metadata = dict(candidate.extraction_metadata or {})
    result = {
        "id": candidate.id,
        "job_id": candidate.job_id,
        "tenant_id": candidate.tenant_id,
        "project_id": candidate.project_id,
        "source_sha256": candidate.source_sha256,
        "src_lang": candidate.src_lang,
        "tgt_lang": candidate.tgt_lang,
        "source_term": candidate.source_term,
        "source_norm": candidate.source_norm,
        "observed_target": candidate.observed_target,
        "suggested_target": candidate.suggested_target,
        "term_type": candidate.term_type,
        "risk": candidate.risk,
        "status": candidate.status,
        "match_type": candidate.match_type,
        "confidence": candidate.confidence,
        "concept_id": candidate.concept_id,
        "termbase_version": candidate.termbase_version,
        "source_context": candidate.source_context,
        "target_context": candidate.target_context,
        "confirmed_target": confirmed_target,
        "extraction_metadata": metadata,
        "extraction_reason": metadata.get("reason"),
        "rule_version": metadata.get("rule_version"),
        "reviewed_by": candidate.reviewed_by,
        "reviewed_at": candidate.reviewed_at.isoformat() if candidate.reviewed_at else None,
        "decision_note": candidate.decision_note,
        "version": candidate.version,
        "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
        "updated_at": candidate.updated_at.isoformat() if candidate.updated_at else None,
    }
    if include_occurrences:
        result["occurrences"] = [
            {
                "id": occurrence.id,
                "page_no": occurrence.page_no,
                "block_id": occurrence.block_id,
                "object_id": occurrence.object_id,
                "char_start": occurrence.char_start,
                "char_end": occurrence.char_end,
                "bbox": occurrence.bbox,
                "source_context": occurrence.source_context,
                "target_context": occurrence.target_context,
            }
            for occurrence in candidate.occurrences
        ]
        result["occurrence_count"] = len(candidate.occurrences)
    return result


def collapse_decided_source_rows(rows: list[dict]) -> list[dict]:
    """已批准/已拒绝列表同一规范化源词只保留一行，避免实际译法不同造成重复。"""
    seen: set[str] = set()
    collapsed: list[dict] = []
    for row in rows:
        status = str(row.get("status") or "")
        key = str(row.get("source_norm") or row.get("source_term") or "").strip().casefold()
        if status in {"approved", "rejected"} and key:
            if key in seen:
                continue
            seen.add(key)
        collapsed.append(row)
    return collapsed


def sort_review_candidates(rows: list[dict]) -> list[dict]:
    """待确认优先看高频新词；高风险靠后。"""

    def rank(row: dict) -> tuple[int, int, int]:
        occ = len(row.get("occurrences") or [])
        match = str(row.get("match_type") or "").casefold()
        known = 1 if match in {"exact", "alias", "termbase"} else 0
        high = 1 if str(row.get("risk") or "").casefold() in {"high", "critical"} else 0
        return (high, known, -occ)

    return sorted(rows, key=rank)


def load_rejected_suppress_index(
    session: Session, *, tenant_id: str, project_id: str | None = None
) -> RejectedIndex:
    """读取本租户/项目下人工拒绝与不译的源词，供抽取时压制。"""
    stmt = (
        select(TermDecision.source_term)
        .join(DocumentTermCandidate)
        .where(TermDecision.action.in_(("reject", "do_not_translate")))
        .where(DocumentTermCandidate.tenant_id == tenant_id)
    )
    if project_id:
        stmt = stmt.where(
            or_(
                TermDecision.scope.in_(("org", "global")),
                DocumentTermCandidate.project_id == project_id,
            )
        )
    sources = [str(item or "").strip() for item in session.scalars(stmt).all() if item]
    if not sources:
        return EMPTY_REJECTED_INDEX
    return build_rejected_index(sources)


def find_concept_by_source_norm(
    session: Session,
    *,
    tenant_id: str,
    project_id: str | None,
    source_norm: str,
    src_lang: str = "en",
) -> Concept | None:
    """按规范化源词查找已 curated 的 Concept。"""
    normalized = normalize_source(source_norm)
    if not normalized:
        return None
    lang = normalize_lang(src_lang) or "en"
    stmt = (
        select(Concept)
        .join(ConceptTerm)
        .where(Concept.status == "curated")
        .where(or_(Concept.tenant_id.is_(None), Concept.tenant_id == tenant_id))
        .where(or_(Concept.project_id.is_(None), Concept.project_id == project_id))
        .where(ConceptTerm.normalized_text == normalized)
        .where(ConceptTerm.lang == lang)
        .options(selectinload(Concept.terms))
    )
    return session.scalars(stmt).first()


def enqueue_candidate(
    session: Session,
    *,
    job: Job,
    translation_run_id: str | None = None,
    tenant_id: str,
    project_id: str,
    source_term: str,
    observed_target: str = "",
    suggested_target: str | None = None,
    term_type: str = "general",
    risk: str = "normal",
    confidence: float = 0.0,
    match_type: str = "candidate",
    src_lang: str = "en",
    tgt_lang: str = "zh",
    source_context: str | None = None,
    target_context: str | None = None,
    termbase_version: str | None = None,
    occurrences: Iterable[dict] | None = None,
    extraction_metadata: dict | None = None,
) -> DocumentTermCandidate:
    """幂等写入一个候选及其出现位置。

    一个 job 中同一规范化源词与同一实际译法只生成一个候选，后续出现位置
    通过 occurrences 追加，避免译后抽取重复污染人工审校队列。
    """
    source = (source_term or "").strip()
    if not source:
        raise ValueError("source_term must not be empty")
    source_norm = normalize_source(source)
    observed = (observed_target or "").strip()
    candidate = session.scalar(
        select(DocumentTermCandidate)
        .where(DocumentTermCandidate.job_id == job.id)
        .where(DocumentTermCandidate.source_norm == source_norm)
        .where(DocumentTermCandidate.observed_target == observed)
        .options(selectinload(DocumentTermCandidate.occurrences))
    )
    if candidate is None:
        candidate = DocumentTermCandidate(
            job_id=job.id,
            translation_run_id=translation_run_id,
            tenant_id=tenant_id,
            project_id=project_id,
            source_sha256=job.source_sha256,
            src_lang=normalize_lang(src_lang) or "en",
            tgt_lang=normalize_lang(tgt_lang) or "zh",
            source_term=source,
            source_norm=source_norm,
            observed_target=observed,
            suggested_target=(suggested_target or "").strip() or None,
            term_type=(term_type or "general").strip() or "general",
            risk=(risk or "normal").strip() or "normal",
            confidence=max(0.0, min(1.0, float(confidence))),
            match_type=(match_type or "candidate").strip() or "candidate",
            source_context=source_context,
            target_context=target_context,
            termbase_version=termbase_version,
            extraction_metadata=dict(extraction_metadata or {}),
            version=1,
        )
        session.add(candidate)
        session.flush()
    else:
        # 抽取重跑时只补充更有信息的建议/上下文，不覆盖人工状态。
        if suggested_target and not candidate.suggested_target:
            candidate.suggested_target = suggested_target.strip()
        if source_context and not candidate.source_context:
            candidate.source_context = source_context
        if target_context and not candidate.target_context:
            candidate.target_context = target_context
        if termbase_version and not candidate.termbase_version:
            candidate.termbase_version = termbase_version
        if translation_run_id and not candidate.translation_run_id:
            candidate.translation_run_id = translation_run_id
        if extraction_metadata and not candidate.extraction_metadata:
            candidate.extraction_metadata = dict(extraction_metadata)

    existing_occurrence_keys = {
        (
            occurrence.page_no,
            occurrence.block_id,
            occurrence.object_id,
            occurrence.char_start,
            occurrence.char_end,
            json.dumps(occurrence.bbox, ensure_ascii=False, sort_keys=True),
            occurrence.source_context,
            occurrence.target_context,
        )
        for occurrence in candidate.occurrences
    }
    for occurrence_data in occurrences or ():
        if not isinstance(occurrence_data, dict):
            raise ValueError("occurrences must contain mapping values")
        occurrence_key = (
            occurrence_data.get("page_no"),
            occurrence_data.get("block_id"),
            occurrence_data.get("object_id"),
            occurrence_data.get("char_start"),
            occurrence_data.get("char_end"),
            json.dumps(occurrence_data.get("bbox"), ensure_ascii=False, sort_keys=True),
            occurrence_data.get("source_context"),
            occurrence_data.get("target_context"),
        )
        if occurrence_key in existing_occurrence_keys:
            continue
        # Keep the already-loaded relationship in sync with the database.  The
        # public extract endpoint serializes this object immediately after the
        # flush; adding only ``candidate_id`` leaves a stale empty collection
        # in that response until the session is refreshed.
        candidate.occurrences.append(
            DocumentTermOccurrence(
                page_no=occurrence_data.get("page_no"),
                block_id=occurrence_data.get("block_id"),
                object_id=occurrence_data.get("object_id"),
                char_start=occurrence_data.get("char_start"),
                char_end=occurrence_data.get("char_end"),
                bbox=occurrence_data.get("bbox"),
                source_context=occurrence_data.get("source_context"),
                target_context=occurrence_data.get("target_context"),
            )
        )
        existing_occurrence_keys.add(occurrence_key)
    session.flush()
    return candidate


def list_candidates(
    session: Session,
    *,
    tenant_id: str,
    job_id: str | None = None,
    project_id: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[DocumentTermCandidate]:
    """按租户强制隔离候选；job/project 过滤均为同一作用域内过滤。"""
    stmt = select(DocumentTermCandidate).where(
        DocumentTermCandidate.tenant_id == tenant_id
    )
    if job_id:
        stmt = stmt.where(DocumentTermCandidate.job_id == job_id)
    if project_id:
        stmt = stmt.where(DocumentTermCandidate.project_id == project_id)
    if status:
        stmt = stmt.where(DocumentTermCandidate.status == status)
    stmt = (
        stmt.options(selectinload(DocumentTermCandidate.occurrences))
        .order_by(DocumentTermCandidate.created_at.asc())
        .limit(max(1, min(int(limit), 1000)))
    )
    return list(session.scalars(stmt).unique().all())


def get_candidate(
    session: Session, *, candidate_id: str, tenant_id: str, job_id: str | None = None
) -> DocumentTermCandidate | None:
    stmt = select(DocumentTermCandidate).where(
        DocumentTermCandidate.id == candidate_id,
        DocumentTermCandidate.tenant_id == tenant_id,
    )
    if job_id:
        stmt = stmt.where(DocumentTermCandidate.job_id == job_id)
    return session.scalar(
        stmt.options(selectinload(DocumentTermCandidate.occurrences))
    )


def _add_curated_concept(
    session: Session,
    *,
    candidate: DocumentTermCandidate,
    target_term: str,
    actor_sub: str,
    scope: str,
    do_not_translate: bool = False,
    concept_id: str | None = None,
    aliases: Iterable[str] | None = None,
    abbreviations: Iterable[str] | None = None,
) -> Concept:
    normalized_scope = (scope or "project").strip().casefold() or "project"
    if normalized_scope not in {"project", "org", "form", "clinical"}:
        raise ValueError(f"unsupported candidate scope: {normalized_scope}")

    def attach_aliases(concept: Concept) -> None:
        existing_normalized = {
            (term.lang.casefold(), normalize_source(term.text))
            for term in concept.terms
        }
        source_lang = normalize_lang(candidate.src_lang) or "en"
        values = [
            *((value, "abbreviation") for value in abbreviations or ()),
            *((value, "synonym") for value in aliases or ()),
        ]
        changed = False
        for value, role in values:
            text = str(value or "").strip()
            normalized = normalize_source(text)
            if not normalized or (source_lang, normalized) in existing_normalized:
                continue
            session.add(
                ConceptTerm(
                    concept_id=concept.id,
                    lang=source_lang,
                    text=text,
                    normalized_text=normalized,
                    role=role,
                )
            )
            existing_normalized.add((source_lang, normalized))
            changed = True
        if changed:
            concept.version += 1

    if concept_id:
        concept = session.get(Concept, concept_id)
        if concept is None:
            raise ValueError("concept_id does not exist")
        if concept.tenant_id not in {None, candidate.tenant_id}:
            raise ValueError("concept is outside tenant scope")
        if concept.project_id not in {None, candidate.project_id}:
            raise ValueError("concept is outside project scope")
        attach_aliases(concept)
        session.flush()
        return concept

    concept = Concept(
        domain="clinical",
        status="curated",
        version=1,
        evidence=f"document_term_candidate:{candidate.id};approved_by:{actor_sub}",
        do_not_translate=do_not_translate,
        layer=normalized_scope,
        tenant_id=candidate.tenant_id,
        project_id=candidate.project_id,
        term_type=candidate.term_type or "general",
        import_key=None,
    )
    session.add(concept)
    session.flush()
    session.add(
        ConceptTerm(
            concept_id=concept.id,
            lang=normalize_lang(candidate.src_lang) or "en",
            text=candidate.source_term,
            normalized_text=normalize_source(candidate.source_term),
            role="preferred",
        )
    )
    session.add(
        ConceptTerm(
            concept_id=concept.id,
            lang=normalize_lang(candidate.tgt_lang) or "zh",
            text=target_term,
            normalized_text=normalize_source(target_term),
            role="preferred",
        )
    )
    attach_aliases(concept)
    session.flush()
    return concept


def decide_candidate(
    session: Session,
    *,
    candidate: DocumentTermCandidate,
    actor_sub: str,
    action: str,
    expected_version: int,
    target_term: str | None = None,
    concept_id: str | None = None,
    note: str | None = None,
    scope: str = "project",
    aliases: Iterable[str] | None = None,
    abbreviations: Iterable[str] | None = None,
) -> dict:
    """以乐观锁完成候选裁决，并在批准类动作时写入正式项目词库。"""
    action = (action or "").strip().casefold()
    scope = (scope or "project").strip().casefold() or "project"
    if action not in VALID_DECISIONS:
        raise ValueError(f"unsupported candidate decision: {action}")
    if candidate.version != expected_version:
        raise CandidateConflict(
            f"candidate version {candidate.version} does not match {expected_version}"
        )
    if action == "submit_for_admin":
        if candidate.status != "pending":
            raise CandidateConflict(f"candidate is already {candidate.status}")
    elif candidate.status not in {"pending", "pending_admin", "violation"}:
        raise CandidateConflict(f"candidate is already {candidate.status}")

    target = (target_term or candidate.suggested_target or candidate.observed_target or "").strip()
    concept: Concept | None = None
    extra_aliases = [str(item).strip() for item in (aliases or ()) if str(item).strip()]
    resolved_concept_id = (concept_id or "").strip() or None
    if (
        action == "approve"
        and not resolved_concept_id
        and has_prefix(candidate.source_term)
    ):
        stem_concept = find_concept_by_source_norm(
            session,
            tenant_id=candidate.tenant_id,
            project_id=candidate.project_id,
            source_norm=morphology_stem(candidate.source_term),
            src_lang=candidate.src_lang,
        )
        if stem_concept is not None:
            resolved_concept_id = stem_concept.id
            extra_aliases.append(candidate.source_term)
    if action == "submit_for_admin":
        candidate.status = "pending_admin"
    elif action in {"approve", "do_not_translate"}:
        if not target and action == "approve":
            raise ValueError("target_term is required when approving a candidate")
        concept = _add_curated_concept(
            session,
            candidate=candidate,
            target_term=target or candidate.source_term,
            actor_sub=actor_sub,
            scope=scope,
            do_not_translate=action == "do_not_translate",
            concept_id=resolved_concept_id,
            aliases=extra_aliases,
            abbreviations=abbreviations,
        )
        candidate.status = "approved"
        candidate.concept_id = concept.id
        candidate.suggested_target = target or candidate.source_term
    elif action == "merge":
        if not concept_id:
            raise ValueError("concept_id is required when merging a candidate")
        concept = _add_curated_concept(
            session,
            candidate=candidate,
            target_term=target or candidate.source_term,
            actor_sub=actor_sub,
            scope=scope,
            concept_id=concept_id,
            aliases=aliases,
            abbreviations=abbreviations,
        )
        candidate.status = "approved"
        candidate.concept_id = concept.id
    else:
        candidate.status = "rejected"

    from_version = candidate.version
    candidate.version += 1
    candidate.reviewed_by = actor_sub
    candidate.reviewed_at = _utcnow()
    candidate.decision_note = note
    session.add(
        TermDecision(
            candidate_id=candidate.id,
            action=action,
            actor_sub=actor_sub,
            source_term=candidate.source_term,
            target_term=target,
            concept_id=concept.id if concept else None,
            scope=(scope or "project").strip().casefold() or "project",
            from_version=from_version,
            to_version=candidate.version,
            note=note,
        )
    )
    session.flush()
    return {
        "candidate": candidate_to_dict(candidate),
        "concept_id": concept.id if concept else None,
    }


def decide_same_source_siblings(
    session: Session,
    *,
    candidate: DocumentTermCandidate,
    actor_sub: str,
    action: str,
    target_term: str | None = None,
    concept_id: str | None = None,
    note: str | None = None,
) -> int:
    """同一 job 里相同 source_norm 的待处理行跟主决定走，避免保存后列表里还剩副本。"""
    if action not in {"approve", "reject", "do_not_translate", "merge"}:
        return 0
    siblings = session.scalars(
        select(DocumentTermCandidate).where(
            DocumentTermCandidate.job_id == candidate.job_id,
            DocumentTermCandidate.source_norm == candidate.source_norm,
            DocumentTermCandidate.id != candidate.id,
            DocumentTermCandidate.status.in_(("pending", "pending_admin", "violation")),
        )
    ).all()
    applied = 0
    for sibling in siblings:
        decide_candidate(
            session,
            candidate=sibling,
            actor_sub=actor_sub,
            action=action,
            expected_version=sibling.version,
            target_term=target_term,
            concept_id=concept_id,
            note=note,
        )
        applied += 1
    return applied


def record_machine_decision(
    session: Session,
    *,
    candidate: DocumentTermCandidate,
    actor_sub: str,
    action: str,
    note: str | None = None,
    concept_id: str | None = None,
) -> TermDecision:
    """PLAN-063e：机器裁决写 TermDecision，不触发人工 approve 的词库副作用。"""
    action = (action or "").strip().casefold()
    from_version = int(candidate.version or 1)
    candidate.version = from_version + 1
    candidate.reviewed_by = actor_sub
    candidate.reviewed_at = _utcnow()
    candidate.decision_note = note
    if action == "apply":
        candidate.status = "applied"
        if concept_id:
            candidate.concept_id = concept_id
    elif action == "reject":
        candidate.status = "rejected"
    decision = TermDecision(
        candidate_id=candidate.id,
        action=action,
        actor_sub=actor_sub,
        source_term=candidate.source_term,
        target_term=candidate.suggested_target or candidate.observed_target or "",
        concept_id=concept_id or candidate.concept_id,
        scope="project",
        from_version=from_version,
        to_version=candidate.version,
        note=note,
    )
    session.add(decision)
    session.flush()
    return decision
