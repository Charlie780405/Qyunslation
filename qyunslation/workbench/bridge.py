# SPDX-License-Identifier: MPL-2.0
"""PLAN-060 internal workbench facade.

This router intentionally has no public prefix.  Caddy must not proxy it: the
only supported caller is the local Gradio process authenticated by the HMAC
dependency in :mod:`qyunslation.workbench.security`.
"""
from __future__ import annotations

import os
import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from qyunslation.api.v1 import get_db
from qyunslation.glossary.termbase import resolve_runtime_terms, runtime_termbase_version
from qyunslation.glossary.term_policy import compile_term_policy, policy_to_glossary
from qyunslation.persist import repo
from qyunslation.persist.audit import record_audit
from qyunslation.persist.candidate_repo import (
    CandidateConflict,
    candidate_to_dict,
    collapse_decided_source_rows,
    decide_candidate,
    decide_same_source_siblings,
    enqueue_candidate,
    get_candidate,
    list_candidates,
    load_rejected_suppress_index,
    sort_review_candidates,
)
from qyunslation.persist.models import WorkbenchTranslationRun
from qyunslation.glossary.candidate_rules import EXCLUDE_REJECTED, should_exclude_from_termbase
from qyunslation.glossary.term_morphology import is_rejected_source
from qyunslation.glossary.term_screen import DECISION_DOMAIN, screen_terms
from qyunslation.workbench.evidence import (
    BilingualTermEvidence,
    classify_risk,
    collect_abbrev_candidates,
    extract_term_pairs_with_stats,
)
from qyunslation.workbench.term_align import (
    MATCH_TERMBASE,
    prefer_explicit_observation,
    align_by_paragraph_batch,
    align_observed,
    suggest_from_termbase,
    suggest_targets,
)
from qyunslation.workbench.security import require_signed_loopback

router = APIRouter(
    prefix="/internal/workbench/v1",
    tags=["Internal workbench"],
    dependencies=[Depends(require_signed_loopback)],
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TENANT_ENV = "QYUNSLATION_WORKBENCH_TENANT"
_ADMIN_ROLES = frozenset({"term_admin", "admin", "owner"})
_HIGH_RISK = frozenset({"high", "critical"})


class StartRunBody(BaseModel):
    actor_sub: str = Field(min_length=1, max_length=256)
    source_sha256: str = Field(min_length=64, max_length=64)
    source_text: str = Field(min_length=1, max_length=2_000_000)
    src_lang: str = Field(default="en", min_length=2, max_length=16)
    tgt_lang: str = Field(default="zh", min_length=2, max_length=16)
    source_format: str = Field(default="unknown", min_length=1, max_length=32)
    external_task_id: str | None = Field(default=None, max_length=256)


class EvidenceBody(BaseModel):
    source_text: str = Field(min_length=1, max_length=20_000)
    target_text: str = Field(default="", max_length=20_000)
    role: str = Field(default="body", max_length=64)
    page_no: int | None = Field(default=None, ge=1)
    block_id: str | None = Field(default=None, max_length=128)
    object_id: str | None = Field(default=None, max_length=128)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    bbox: dict | None = None
    source_term: str | None = Field(default=None, max_length=512)
    target_term: str | None = Field(default=None, max_length=512)
    term_type: str | None = Field(default=None, max_length=64)

    def as_evidence(self) -> BilingualTermEvidence:
        return BilingualTermEvidence(**self.model_dump())


class CompleteRunBody(BaseModel):
    actor_sub: str = Field(min_length=1, max_length=256)
    evidence: list[EvidenceBody] = Field(default_factory=list, max_length=1000)
    degradation_reason: str | None = Field(default=None, max_length=256)


class DecisionBody(BaseModel):
    actor_sub: str = Field(min_length=1, max_length=256)
    action: Literal["approve", "reject", "merge", "do_not_translate", "submit_for_admin"]
    expected_version: int = Field(ge=1)
    target_term: str | None = Field(default=None, max_length=512)
    concept_id: str | None = Field(default=None, max_length=36)
    note: str | None = Field(default=None, max_length=10_000)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    abbreviations: list[str] = Field(default_factory=list, max_length=20)


class BatchDecisionItem(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=36)
    action: Literal["approve", "reject", "do_not_translate"]
    expected_version: int = Field(ge=1)
    target_term: str | None = Field(default=None, max_length=512)
    concept_id: str | None = Field(default=None, max_length=36)
    note: str | None = Field(default=None, max_length=10_000)


class BatchDecisionBody(BaseModel):
    actor_sub: str = Field(min_length=1, max_length=256)
    decisions: list[BatchDecisionItem] = Field(min_length=1, max_length=100)


def _tenant_slug() -> str:
    value = (os.environ.get(_TENANT_ENV) or "").strip()
    if not value:
        raise HTTPException(status_code=503, detail="workbench term bridge unavailable")
    return value


def _tenant_context(session: Session, actor_sub: str):
    tenant = repo.get_or_create_tenant(session, slug=_tenant_slug())
    membership = repo.ensure_membership(session, tenant_id=tenant.id, user_sub=actor_sub)
    return tenant, membership


def _run_for_actor(
    session: Session, *, run_id: str, actor_sub: str
) -> tuple[WorkbenchTranslationRun, Any, Any]:
    tenant, membership = _tenant_context(session, actor_sub)
    run = session.get(WorkbenchTranslationRun, run_id)
    if run is None or run.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="workbench run not found")
    if run.actor_sub != actor_sub and membership.role not in _ADMIN_ROLES:
        # Return 404 to avoid exposing another employee's file-derived data.
        raise HTTPException(status_code=404, detail="workbench run not found")
    return run, tenant, membership


def _policy_response(policy: dict) -> dict:
    result = dict(policy)
    result["hard_terms"] = policy_to_glossary(policy)
    result["semantic_used"] = False
    return result


def _is_applied(policy: dict, evidence: BilingualTermEvidence, source_term: str) -> tuple[bool, str | None]:
    source = source_term.casefold()
    for term in policy.get("terms", []):
        if not term.get("hard_constraint"):
            continue
        preferred = str(term.get("preferred_target") or "").strip()
        configured_source = str(term.get("source_term") or "").strip()
        if configured_source.casefold() != source or not preferred:
            continue
        # A workflow may report an explicit target span.  Otherwise use a
        # target-context containment check before claiming the constraint held.
        observed = (evidence.target_term or evidence.target_text or "").strip()
        if preferred.casefold() in observed.casefold():
            return True, preferred
        return False, preferred
    return False, None


def _extract_candidates(
    session: Session,
    *,
    run: WorkbenchTranslationRun,
    tenant_id: str,
    policy: dict,
    evidence: list[BilingualTermEvidence],
) -> tuple[list[dict], dict]:
    job = repo.get_job(session, job_id=run.job_id)
    if job is None:  # database invariant; do not turn it into a 500 leak
        raise HTTPException(status_code=404, detail="workbench job not found")
    candidate_ids: set[str] = set()
    excluded_stats: dict[str, int] = {}
    screen_origin: dict[str, int] = {}
    rejected_index = load_rejected_suppress_index(
        session, tenant_id=tenant_id, project_id=job.project_id
    )
    seen_occurrences: set[
        tuple[str, str, int | None, str | None, str | None, int | None, int | None]
    ] = set()

    def note_exclude(reason: str) -> None:
        excluded_stats[reason] = excluded_stats.get(reason, 0) + 1

    def append_candidate(
        *,
        source_term: str,
        observed_target: str,
        suggested_target: str | None,
        term_type: str,
        match_type: str,
        confidence: float,
        status: str,
        extracted: dict,
        allow_excluded: bool = False,
    ) -> None:
        if not allow_excluded:
            excluded, reason = should_exclude_from_termbase(source_term)
            if excluded:
                note_exclude(reason)
                return
            if is_rejected_source(source_term, rejected_index):
                note_exclude(EXCLUDE_REJECTED)
                return
        occurrence = (extracted.get("occurrences") or [{}])[0]
        key = (
            source_term.casefold(),
            observed_target.casefold(),
            occurrence.get("page_no"),
            occurrence.get("block_id"),
            occurrence.get("object_id"),
            occurrence.get("char_start"),
            occurrence.get("char_end"),
        )
        if key in seen_occurrences:
            return
        seen_occurrences.add(key)
        candidate = enqueue_candidate(
            session,
            job=job,
            tenant_id=tenant_id,
            project_id=job.project_id,
            source_term=source_term,
            observed_target=observed_target,
            suggested_target=suggested_target,
            term_type=term_type,
            risk=classify_risk(source_term, term_type),
            confidence=confidence,
            match_type=match_type,
            src_lang=job.provenance.get("src_lang", "en") if job.provenance else "en",
            tgt_lang=job.provenance.get("tgt_lang", "zh") if job.provenance else "zh",
            source_context=extracted["source_context"],
            target_context=extracted["target_context"],
            termbase_version=run.termbase_version,
            occurrences=extracted["occurrences"],
        )
        if candidate.status == "pending" and status in {"applied", "violation"}:
            candidate.status = status
        candidate_ids.add(candidate.id)

    staged: list[dict] = []
    screen_jobs: list[tuple[BilingualTermEvidence, str]] = []
    for item in evidence:
        if not item.is_translatable:
            continue
        context = {
            "source_context": item.source_text[:1000],
            "target_context": item.target_text[:1000],
            "occurrences": [item.occurrence()],
        }
        # Normal page/paragraph evidence need not already contain term spans:
        # known hard terms are still checked against the aligned target text.
        for term in policy.get("terms", []):
            if not term.get("hard_constraint"):
                continue
            source_term = str(term.get("source_term") or "").strip()
            preferred = str(term.get("preferred_target") or "").strip()
            if not source_term or not preferred or source_term.casefold() not in item.source_text.casefold():
                continue
            applied = preferred.casefold() in item.target_text.casefold()
            append_candidate(
                source_term=source_term,
                observed_target=preferred if applied else "",
                suggested_target=preferred,
                term_type=str(term.get("term_type") or "general"),
                match_type="exact",
                confidence=1.0,
                status="applied" if applied else "violation",
                extracted=context,
                allow_excluded=True,
            )
        extracted_rows, extract_stats = extract_term_pairs_with_stats([item])
        for reason, count in extract_stats.items():
            excluded_stats[reason] = excluded_stats.get(reason, 0) + count
        for source_term in collect_abbrev_candidates(item.source_text):
            screen_jobs.append((item, source_term))
        for extracted in extracted_rows:
            if is_rejected_source(extracted["source_term"], rejected_index):
                note_exclude(EXCLUDE_REJECTED)
                continue
            aligned = prefer_explicit_observation(
                extracted,
                align_observed(
                    extracted["source_term"],
                    source_context=extracted["source_context"],
                    target_context=extracted["target_context"],
                    policy=policy,
                ),
            )
            staged.append({"item": item, "extracted": extracted, "aligned": aligned})
    if screen_jobs:
        verdicts = screen_terms(
            [term for _item, term in screen_jobs],
            session=session,
            tenant_id=tenant_id,
            project_id=job.project_id,
            persist=True,
        )
        for verdict in verdicts.values():
            screen_origin[verdict.origin] = screen_origin.get(verdict.origin, 0) + 1
        for item, source_term in screen_jobs:
            verdict = verdicts.get(source_term)
            if verdict is None or verdict.decision != DECISION_DOMAIN:
                reason = "SCREEN_NOISE" if verdict is not None and verdict.decision == "noise" else "SCREEN_GENERIC"
                excluded_stats[reason] = excluded_stats.get(reason, 0) + 1
                continue
            if is_rejected_source(source_term, rejected_index):
                note_exclude(EXCLUDE_REJECTED)
                continue
            extracted = {
                "source_term": source_term,
                "observed_target": "",
                "term_type": verdict.term_type,
                "source_context": item.source_text[:1000],
                "target_context": item.target_text[:1000],
                "occurrences": [item.occurrence()],
            }
            staged.append(
                {
                    "item": item,
                    "extracted": extracted,
                    "aligned": prefer_explicit_observation(
                        extracted,
                        align_observed(
                            source_term,
                            source_context=extracted["source_context"],
                            target_context=extracted["target_context"],
                            policy=policy,
                        ),
                    ),
                }
            )
    suggestions = suggest_from_termbase(
        staged,
        policy=policy,
        session=session,
        tenant_id=tenant_id,
        project_id=job.project_id,
        src_lang=str((job.provenance or {}).get("src_lang") or "en"),
        tgt_lang=str((job.provenance or {}).get("tgt_lang") or "zh"),
    )
    remaining = [row for row in staged if row["extracted"]["source_term"] not in suggestions]
    suggestions.update(align_by_paragraph_batch(remaining))
    suggestions.update(
        suggest_targets(
            [row for row in remaining if row["extracted"]["source_term"] not in suggestions]
        )
    )
    for row in staged:
        item = row["item"]
        extracted = row["extracted"]
        aligned = suggestions.get(extracted["source_term"], row["aligned"])
        source_term = extracted["source_term"]
        applied, preferred = _is_applied(policy, item, source_term)
        observed_target = aligned.observed_target or extracted["observed_target"]
        match_type = aligned.match_type
        status = "pending"
        suggested_target = aligned.suggested_target
        confidence = aligned.confidence
        if preferred is not None:
            match_type = "exact"
            suggested_target = preferred
            confidence = 1.0
            if applied:
                status = "applied"
                observed_target = preferred
            else:
                status = "violation"
        elif aligned.match_type == MATCH_TERMBASE and aligned.observed_target:
            status = "applied"
        append_candidate(
            source_term=source_term,
            observed_target=observed_target,
            suggested_target=suggested_target,
            term_type=extracted["term_type"],
            match_type=match_type,
            confidence=confidence,
            status=status,
            extracted=extracted,
        )
    # Reload through the repository to include every idempotently aggregated
    # occurrence, rather than returning the first occurrence only.
    rows = list_candidates(session, tenant_id=tenant_id, job_id=job.id, limit=1000)
    payload: dict = dict(excluded_stats)
    payload["screen_origin"] = screen_origin
    payload["extracted_total"] = sum(excluded_stats.values()) + len(candidate_ids)
    from qyunslation.glossary.candidate_rules import rules_version

    payload["rules_version"] = rules_version()
    return [candidate_to_dict(row) for row in rows if row.id in candidate_ids], payload


@router.post("/runs/start", status_code=201)
def start_run(body: StartRunBody, session: Session = Depends(get_db)) -> dict:
    digest = body.source_sha256.casefold()
    if not _SHA256_RE.fullmatch(digest):
        raise HTTPException(status_code=400, detail="source_sha256 must be 64 hex chars")
    tenant, _membership = _tenant_context(session, body.actor_sub)
    project = repo.get_or_create_company_termbase_project(session, tenant_id=tenant.id)
    matches = resolve_runtime_terms(
        session,
        tenant_id=tenant.id,
        project_id=project.id,
        text=body.source_text,
        src_lang=body.src_lang,
        tgt_lang=body.tgt_lang,
    )
    version = runtime_termbase_version(session, tenant_id=tenant.id, project_id=project.id)
    policy = compile_term_policy(matches, termbase_version=version)
    job = repo.create_job(
        session,
        project_id=project.id,
        source_sha256=digest,
        status="translating",
        provenance={
            "source_format": body.source_format,
            "src_lang": body.src_lang,
            "tgt_lang": body.tgt_lang,
            "termbase_version": version,
        },
    )
    run = WorkbenchTranslationRun(
        job_id=job.id,
        tenant_id=tenant.id,
        actor_sub=body.actor_sub,
        source_format=body.source_format.casefold(),
        external_task_id=body.external_task_id,
        status="translating",
        termbase_version=version,
        term_policy=policy,
    )
    session.add(run)
    session.flush()
    record_audit(
        session,
        actor_sub=body.actor_sub,
        action="workbench.term_run.start",
        source_sha256=digest,
        extra={"run_id": run.id, "job_id": job.id, "source_format": body.source_format},
    )
    return {
        "run_id": run.id,
        "job_id": job.id,
        "project_id": project.id,
        "policy": _policy_response(policy),
    }


@router.post("/runs/{run_id}/complete")
def complete_run(
    run_id: str, body: CompleteRunBody, session: Session = Depends(get_db)
) -> dict:
    run, tenant, _membership = _run_for_actor(session, run_id=run_id, actor_sub=body.actor_sub)
    evidence = [item.as_evidence() for item in body.evidence]
    policy = run.term_policy or {"schema": "058-term-policy-v1", "terms": []}
    candidates, excluded = _extract_candidates(
        session,
        run=run,
        tenant_id=tenant.id,
        policy=policy,
        evidence=evidence,
    )
    job = repo.get_job(session, job_id=run.job_id)
    assert job is not None
    if body.degradation_reason or not evidence:
        run.status = "extraction_degraded"
        run.degradation_reason = body.degradation_reason or "no_aligned_evidence"
    else:
        run.status = "review_ready"
        run.degradation_reason = None
    job.status = run.status
    run.excluded_stats = excluded
    try:
        from qyunslation.quality.ledger import record_run

        record_run(
            session,
            run=run,
            excluded_stats=excluded,
            candidate_summary=_summary(session, run, tenant.id, excluded=excluded),
        )
    except Exception:
        pass
    record_audit(
        session,
        actor_sub=body.actor_sub,
        action="workbench.term_run.complete",
        source_sha256=job.source_sha256,
        extra={"run_id": run.id, "candidate_count": len(candidates), "status": run.status},
    )
    return {
        "run_id": run.id,
        "status": run.status,
        "candidates": candidates,
        "summary": _summary(session, run, tenant.id, excluded=excluded),
    }


def _summary(
    session: Session,
    run: WorkbenchTranslationRun,
    tenant_id: str,
    excluded: dict[str, int] | None = None,
) -> dict:
    rows = list_candidates(session, tenant_id=tenant_id, job_id=run.job_id, limit=1000)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    high_unresolved = [
        row.id
        for row in rows
        if row.risk.casefold() in _HIGH_RISK
        and row.status not in {"applied", "approved", "rejected"}
    ]
    return {
        "run_id": run.id,
        "status": run.status,
        "degradation_reason": run.degradation_reason,
        "termbase_version": run.termbase_version,
        "total": len(rows),
        "pending": counts.get("pending", 0),
        "pending_admin": counts.get("pending_admin", 0),
        "applied": counts.get("applied", 0),
        "approved": counts.get("approved", 0),
        "rejected": counts.get("rejected", 0),
        "violation": counts.get("violation", 0),
        "formal_gate": {"passed": not high_unresolved, "blocking_candidate_ids": high_unresolved},
        "excluded": excluded or {},
    }


class ConceptSearchBody(BaseModel):
    actor_sub: str = Field(min_length=1, max_length=256)
    query: str = Field(min_length=1, max_length=256)


@router.post("/concepts/search")
def search_concepts(body: ConceptSearchBody, session: Session = Depends(get_db)) -> dict:
    tenant, _membership = _tenant_context(session, body.actor_sub)
    project = repo.get_or_create_company_termbase_project(session, tenant_id=tenant.id)
    matches = resolve_runtime_terms(
        session,
        tenant_id=tenant.id,
        project_id=project.id,
        text=body.query,
        src_lang="en",
        tgt_lang="zh",
    )
    return {
        "matches": [
            {
                "concept_id": match.concept_id,
                "source_term": match.source_term,
                "preferred_target": match.target_term,
                "layer": match.layer,
                "match_type": match.match_type,
                "hard_constraint": match.match_type in {"exact", "alias"},
            }
            for match in matches[:20]
        ]
    }


@router.get("/runs/latest")
def get_latest_run(actor_sub: str, session: Session = Depends(get_db)) -> dict:
    """登录/重启后恢复最近一次可审校任务，避免「已处理」因 Gradio 状态丢失而显示为零。"""
    tenant, membership = _tenant_context(session, actor_sub)
    stmt = (
        select(WorkbenchTranslationRun)
        .where(
            WorkbenchTranslationRun.tenant_id == tenant.id,
            WorkbenchTranslationRun.status.in_(("review_ready", "extraction_degraded")),
        )
        .order_by(WorkbenchTranslationRun.created_at.desc())
        .limit(1)
    )
    if membership.role not in _ADMIN_ROLES:
        stmt = stmt.where(WorkbenchTranslationRun.actor_sub == actor_sub)
    run = session.scalars(stmt).first()
    if run is None:
        raise HTTPException(status_code=404, detail="workbench run not found")
    job = repo.get_job(session, job_id=run.job_id)
    return {
        "run_id": run.id,
        "job_id": run.job_id,
        "project_id": job.project_id if job is not None else None,
        "status": run.status,
        "termbase_version": run.termbase_version,
        "summary": _summary(session, run, tenant.id),
    }


@router.get("/runs/{run_id}/term-review")
def get_term_review(run_id: str, actor_sub: str, session: Session = Depends(get_db)) -> dict:
    run, tenant, _membership = _run_for_actor(session, run_id=run_id, actor_sub=actor_sub)
    rows = list_candidates(session, tenant_id=tenant.id, job_id=run.job_id, limit=200)
    return {
        "summary": _summary(session, run, tenant.id),
        "candidates": sort_review_candidates(
            collapse_decided_source_rows([candidate_to_dict(row) for row in rows])
        ),
    }


def _decide(
    session: Session,
    *,
    run: WorkbenchTranslationRun,
    tenant_id: str,
    actor_sub: str,
    membership: Any,
    candidate_id: str,
    body: DecisionBody,
) -> dict:
    candidate = get_candidate(session, candidate_id=candidate_id, tenant_id=tenant_id, job_id=run.job_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="term candidate not found")
    is_admin = membership.role in _ADMIN_ROLES
    high_risk = candidate.risk.casefold() in _HIGH_RISK
    if body.action == "submit_for_admin":
        if not high_risk:
            raise HTTPException(status_code=400, detail="only high-risk candidates require administrator review")
    elif (
        body.action not in {"do_not_translate", "reject"}
        and (high_risk or candidate.status == "pending_admin")
        and not is_admin
    ):
        raise HTTPException(status_code=403, detail="term_admin role required for high-risk term")
    try:
        result = decide_candidate(
            session,
            candidate=candidate,
            actor_sub=actor_sub,
            action=body.action,
            expected_version=body.expected_version,
            target_term=body.target_term,
            concept_id=body.concept_id,
            note=body.note,
            scope="project",
            aliases=body.aliases,
            abbreviations=body.abbreviations,
        )
    except CandidateConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    decide_same_source_siblings(
        session,
        candidate=candidate,
        actor_sub=actor_sub,
        action=body.action,
        target_term=body.target_term,
        concept_id=result.get("concept_id") or body.concept_id,
        note=body.note,
    )
    job = repo.get_job(session, job_id=run.job_id)
    assert job is not None
    record_audit(
        session,
        actor_sub=actor_sub,
        action=f"workbench.term_candidate.{body.action}",
        source_sha256=job.source_sha256,
        extra={"run_id": run.id, "candidate_id": candidate.id, "concept_id": result.get("concept_id")},
    )
    result["summary"] = _summary(session, run, tenant_id)
    return result


@router.post("/runs/{run_id}/terms/{candidate_id}/decision")
def decide_term(
    run_id: str, candidate_id: str, body: DecisionBody, session: Session = Depends(get_db)
) -> dict:
    run, tenant, membership = _run_for_actor(session, run_id=run_id, actor_sub=body.actor_sub)
    return _decide(
        session,
        run=run,
        tenant_id=tenant.id,
        actor_sub=body.actor_sub,
        membership=membership,
        candidate_id=candidate_id,
        body=body,
    )


@router.post("/runs/{run_id}/terms/batch-decision")
def batch_decide_terms(run_id: str, body: BatchDecisionBody, session: Session = Depends(get_db)) -> dict:
    run, tenant, membership = _run_for_actor(session, run_id=run_id, actor_sub=body.actor_sub)
    decided: list[dict] = []
    for item in body.decisions:
        candidate = get_candidate(session, candidate_id=item.candidate_id, tenant_id=tenant.id, job_id=run.job_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail="term candidate not found")
        if item.action in {"reject", "do_not_translate"}:
            if candidate.status not in {"pending", "pending_admin"}:
                raise HTTPException(status_code=400, detail="candidate is not eligible for batch reject")
        else:
            target = (item.target_term or candidate.suggested_target or candidate.observed_target or "").strip()
            if (
                candidate.status not in {"pending", "pending_admin"}
                or candidate.risk.casefold() in _HIGH_RISK
                or not target
            ):
                raise HTTPException(status_code=400, detail="candidate is not eligible for batch approval")
        decided.append(
            _decide(
                session,
                run=run,
                tenant_id=tenant.id,
                actor_sub=body.actor_sub,
                membership=membership,
                candidate_id=item.candidate_id,
                body=DecisionBody(
                    actor_sub=body.actor_sub,
                    action=item.action,
                    expected_version=item.expected_version,
                    target_term=item.target_term,
                    concept_id=item.concept_id,
                    note=item.note,
                ),
            )
        )
    return {"count": len(decided), "decided": decided, "summary": _summary(session, run, tenant.id)}
