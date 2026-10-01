# SPDX-License-Identifier: MPL-2.0
"""PLAN-034g：审校队列 / 批准→TM / 术语候选 / diff。"""
from __future__ import annotations

import difflib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from qyunslation.persist.concept_repo import create_staging_concept, detect_forbidden
from qyunslation.persist.models import Job, Project, ReviewNote, ReviewRevision, ReviewSegment
from qyunslation.persist.tm_repo import create_approved_unit, lookup

VALID_STATUSES = frozenset({"pending", "approved", "rejected"})
PRESERVE_POLICY = "PRESERVE"
HUMAN_REVIEW_POLICY = "HUMAN_REVIEW"


class ReviewError(ValueError):
    """审校业务错误。"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def segment_to_dict(seg: ReviewSegment, *, include_notes: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": seg.id,
        "translation_run_id": seg.translation_run_id,
        "generation": seg.generation,
        "page_no": seg.page_no,
        "bbox": seg.bbox,
        "job_id": seg.job_id,
        "source_sha256": seg.source_sha256,
        "block_id": seg.block_id,
        "policy": seg.policy,
        "role": seg.role,
        "source_text": seg.source_text,
        "machine_text": seg.machine_text,
        "revised_text": seg.revised_text,
        "status": seg.status,
        "decided_by": seg.decided_by,
        "decided_at": seg.decided_at.isoformat() if seg.decided_at else None,
        "version": seg.version,
        "created_at": seg.created_at.isoformat(),
        "updated_at": seg.updated_at.isoformat(),
    }
    if include_notes:
        notes = list(seg.notes) if seg.notes is not None else []
        out["notes"] = [
            {
                "id": n.id,
                "author_sub": n.author_sub,
                "body": n.body,
                "created_at": n.created_at.isoformat(),
            }
            for n in notes
        ]
    return out


def should_enqueue(policy: str | None) -> bool:
    """PRESERVE 不入队；HUMAN_REVIEW 及其它策略可入队。"""
    p = (policy or "TRANSLATE").strip().upper()
    return p != PRESERVE_POLICY


def job_owned_by_tenant(session: Session, *, job_id: str, tenant_id: str) -> Job | None:
    job = session.get(Job, job_id)
    if job is None:
        return None
    project = session.get(Project, job.project_id)
    if project is None or project.tenant_id != tenant_id:
        return None
    return job


def enqueue_segments(
    session: Session,
    *,
    job: Job,
    items: list[dict[str, Any]],
) -> tuple[list[ReviewSegment], list[dict[str, Any]]]:
    """入队句段；返回 (created, skipped)。"""
    created: list[ReviewSegment] = []
    skipped: list[dict[str, Any]] = []
    for raw in items:
        policy = str(raw.get("policy") or "TRANSLATE").strip().upper()
        source_text = str(raw.get("source_text") or "").strip()
        if not source_text:
            skipped.append({"reason": "empty_source", "item": raw})
            continue
        if not should_enqueue(policy):
            skipped.append({"reason": "preserve", "policy": policy, "block_id": raw.get("block_id")})
            continue
        seg = ReviewSegment(
            job_id=job.id,
            translation_run_id=(str(raw["translation_run_id"]) if raw.get("translation_run_id") else None),
            generation=(int(raw["generation"]) if raw.get("generation") is not None else None),
            page_no=(int(raw["page_no"]) if raw.get("page_no") is not None else None),
            bbox=(dict(raw["bbox"]) if isinstance(raw.get("bbox"), dict) else None),
            source_sha256=job.source_sha256,
            block_id=(str(raw["block_id"]) if raw.get("block_id") else None),
            policy=policy,
            role=str(raw.get("role") or "body"),
            source_text=source_text,
            machine_text=str(raw.get("machine_text") or ""),
            revised_text=None,
            status="pending",
            version=1,
        )
        session.add(seg)
        session.flush()
        # 初版机译记为 revision v1（若有）
        if seg.machine_text:
            session.add(
                ReviewRevision(
                    segment_id=seg.id,
                    source_sha256=job.source_sha256,
                    version=1,
                    target_text=seg.machine_text,
                    action="enqueue",
                    actor_sub="system",
                )
            )
        created.append(seg)
    session.flush()
    return created, skipped


def list_queue(
    session: Session,
    *,
    tenant_id: str,
    job_id: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[ReviewSegment]:
    stmt = (
        select(ReviewSegment)
        .join(Job, ReviewSegment.job_id == Job.id)
        .join(Project, Job.project_id == Project.id)
        .where(Project.tenant_id == tenant_id)
        .options(selectinload(ReviewSegment.notes))
        .order_by(ReviewSegment.created_at.desc())
        .limit(limit)
    )
    if job_id:
        stmt = stmt.where(ReviewSegment.job_id == job_id)
    if status:
        stmt = stmt.where(ReviewSegment.status == status)
    return list(session.scalars(stmt).all())


def get_segment_for_tenant(
    session: Session, *, segment_id: str, tenant_id: str
) -> ReviewSegment | None:
    seg = session.scalar(
        select(ReviewSegment)
        .where(ReviewSegment.id == segment_id)
        .options(selectinload(ReviewSegment.notes), selectinload(ReviewSegment.revisions))
    )
    if seg is None:
        return None
    if job_owned_by_tenant(session, job_id=seg.job_id, tenant_id=tenant_id) is None:
        return None
    return seg


def add_note(
    session: Session,
    *,
    segment: ReviewSegment,
    author_sub: str,
    body: str,
) -> ReviewNote:
    note = ReviewNote(segment_id=segment.id, author_sub=author_sub, body=body.strip())
    session.add(note)
    session.flush()
    return note


def decide_segment(
    session: Session,
    *,
    segment: ReviewSegment,
    tenant_id: str,
    actor_sub: str,
    action: str,
    revised_text: str | None = None,
    promote_term: bool = False,
    project_id: str | None = None,
    src_lang: str = "en",
    tgt_lang: str = "zh",
) -> dict[str, Any]:
    """approve → TM；可选 staging concept；reject 不写 TM。"""
    act = (action or "").strip().lower()
    if act not in {"approve", "reject"}:
        raise ReviewError("action must be approve or reject")
    if segment.status != "pending":
        raise ReviewError(f"segment already decided: {segment.status}")

    final_text = (revised_text if revised_text is not None else None)
    if final_text is None:
        final_text = segment.revised_text or segment.machine_text or ""
    final_text = final_text.strip()
    if act == "approve" and not final_text:
        raise ReviewError("approved segment requires non-empty target text")

    now = _utcnow()
    segment.revised_text = final_text if act == "approve" else (revised_text or segment.revised_text)
    segment.status = "approved" if act == "approve" else "rejected"
    segment.decided_by = actor_sub
    segment.decided_at = now
    segment.version = int(segment.version or 1) + 1
    segment.updated_at = now

    rev = ReviewRevision(
        segment_id=segment.id,
        source_sha256=segment.source_sha256,
        version=segment.version,
        target_text=final_text or (segment.machine_text or ""),
        action=act,
        actor_sub=actor_sub,
    )
    session.add(rev)
    session.flush()

    tm_unit = None
    concept = None
    if act == "approve":
        tm_unit = create_approved_unit(
            session,
            tenant_id=tenant_id,
            source_text=segment.source_text,
            target_text=final_text,
            approved=True,
            approved_by=actor_sub,
            project_id=project_id,
            src_lang=src_lang,
            tgt_lang=tgt_lang,
        )
        if promote_term:
            concept = create_staging_concept(
                session,
                preferred_source=segment.source_text[:512],
                preferred_target=final_text[:512],
                layer="session",
                src_lng=src_lang,
                tgt_lng=tgt_lang,
                evidence=f"review_segment:{segment.id}",
                tenant_id=tenant_id,
            )

    return {
        "segment": segment_to_dict(segment),
        "tm_unit_id": tm_unit.id if tm_unit else None,
        "concept_id": concept.id if concept else None,
        "revision_version": rev.version,
    }


def list_revisions(
    session: Session,
    *,
    tenant_id: str,
    source_sha256: str | None = None,
    segment_id: str | None = None,
) -> list[ReviewRevision]:
    stmt = (
        select(ReviewRevision)
        .join(ReviewSegment, ReviewRevision.segment_id == ReviewSegment.id)
        .join(Job, ReviewSegment.job_id == Job.id)
        .join(Project, Job.project_id == Project.id)
        .where(Project.tenant_id == tenant_id)
        .order_by(ReviewRevision.version.asc())
    )
    if source_sha256:
        stmt = stmt.where(ReviewRevision.source_sha256 == source_sha256.lower())
    if segment_id:
        stmt = stmt.where(ReviewRevision.segment_id == segment_id)
    return list(session.scalars(stmt).all())


def diff_revisions(
    session: Session,
    *,
    tenant_id: str,
    source_sha256: str | None = None,
    segment_id: str | None = None,
    version_a: int | None = None,
    version_b: int | None = None,
) -> dict[str, Any]:
    revs = list_revisions(
        session,
        tenant_id=tenant_id,
        source_sha256=source_sha256,
        segment_id=segment_id,
    )
    if len(revs) < 2 and not (version_a and version_b):
        if len(revs) < 2:
            return {"hunks": [], "a": None, "b": None, "note": "need at least two revisions"}
    by_ver = {r.version: r for r in revs}
    if version_a is not None and version_b is not None:
        ra = by_ver.get(version_a)
        rb = by_ver.get(version_b)
    else:
        ra, rb = revs[0], revs[-1]
    if ra is None or rb is None:
        raise ReviewError("revision version not found")
    hunks = list(
        difflib.unified_diff(
            (ra.target_text or "").splitlines(),
            (rb.target_text or "").splitlines(),
            fromfile=f"v{ra.version}",
            tofile=f"v{rb.version}",
            lineterm="",
        )
    )
    return {
        "a": {"version": ra.version, "target_text": ra.target_text, "action": ra.action},
        "b": {"version": rb.version, "target_text": rb.target_text, "action": rb.action},
        "hunks": hunks,
    }


def suggestions(
    session: Session,
    *,
    tenant_id: str,
    source_text: str,
    target_text: str | None = None,
    project_id: str | None = None,
    forbidden: list[str] | None = None,
) -> dict[str, Any]:
    """TM lookup + forbidden；确认前不入库。"""
    hit = lookup(
        session,
        tenant_id=tenant_id,
        source_text=source_text,
        project_id=project_id,
    )
    forbidden_hit = False
    if target_text and forbidden:
        forbidden_hit = detect_forbidden(target_text, forbidden)
    return {
        "tm": hit,
        "forbidden_hit": forbidden_hit,
        "note": "suggestions only; confirm via decide before TM/term write",
    }
