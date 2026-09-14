# SPDX-License-Identifier: MPL-2.0
"""PLAN-058：译后术语候选、出现位置与人工裁决仓储。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from qyunslation.glossary.governance import normalize_lang, normalize_source
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


VALID_DECISIONS = frozenset({"approve", "reject", "merge", "do_not_translate"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def candidate_to_dict(
    candidate: DocumentTermCandidate, *, include_occurrences: bool = True
) -> dict:
    """将候选序列化为 API/UI 可直接消费的稳定结构。"""
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
    return result


def enqueue_candidate(
    session: Session,
    *,
    job: Job,
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

    for occurrence_data in occurrences or ():
        if not isinstance(occurrence_data, dict):
            raise ValueError("occurrences must contain mapping values")
        session.add(
            DocumentTermOccurrence(
                candidate_id=candidate.id,
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
) -> Concept:
    if concept_id:
        concept = session.get(Concept, concept_id)
        if concept is None:
            raise ValueError("concept_id does not exist")
        if concept.tenant_id not in {None, candidate.tenant_id}:
            raise ValueError("concept is outside tenant scope")
        if concept.project_id not in {None, candidate.project_id}:
            raise ValueError("concept is outside project scope")
        return concept

    concept = Concept(
        domain="clinical",
        status="curated",
        version=1,
        evidence=f"document_term_candidate:{candidate.id};approved_by:{actor_sub}",
        do_not_translate=do_not_translate,
        layer=(scope or "project").strip().casefold() or "project",
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
) -> dict:
    """以乐观锁完成候选裁决，并在批准类动作时写入正式项目词库。"""
    action = (action or "").strip().casefold()
    if action not in VALID_DECISIONS:
        raise ValueError(f"unsupported candidate decision: {action}")
    if candidate.version != expected_version:
        raise CandidateConflict(
            f"candidate version {candidate.version} does not match {expected_version}"
        )
    if candidate.status != "pending":
        raise CandidateConflict(f"candidate is already {candidate.status}")

    target = (target_term or candidate.suggested_target or candidate.observed_target or "").strip()
    concept: Concept | None = None
    if action in {"approve", "do_not_translate"}:
        if not target and action == "approve":
            raise ValueError("target_term is required when approving a candidate")
        concept = _add_curated_concept(
            session,
            candidate=candidate,
            target_term=target or candidate.source_term,
            actor_sub=actor_sub,
            scope=scope,
            do_not_translate=action == "do_not_translate",
            concept_id=concept_id,
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
