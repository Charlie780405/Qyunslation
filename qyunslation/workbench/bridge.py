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
from sqlalchemy.orm import Session

from qyunslation.api.v1 import get_db
from qyunslation.glossary.termbase import resolve_runtime_terms, runtime_termbase_version
from qyunslation.glossary.term_policy import compile_term_policy, policy_to_glossary
from qyunslation.persist import repo
from qyunslation.persist.audit import record_audit
from qyunslation.persist.candidate_repo import (
    CandidateConflict,
    candidate_to_dict,
    decide_candidate,
    enqueue_candidate,
    get_candidate,
    list_candidates,
)
from qyunslation.persist.models import WorkbenchTranslationRun
from qyunslation.workbench.evidence import (
    BilingualTermEvidence,
    classify_risk,
    extract_term_pairs,
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


class BatchDecisionItem(DecisionBody):
    candidate_id: str = Field(min_length=1, max_length=36)


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
) -> list[dict]:
    job = repo.get_job(session, job_id=run.job_id)
    if job is None:  # database invariant; do not turn it into a 500 leak
        raise HTTPException(status_code=404, detail="workbench job not found")
    serialized: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in evidence:
        for extracted in extract_term_pairs([item]):
            source_term = extracted["source_term"]
            applied, preferred = _is_applied(policy, item, source_term)
            observed_target = extracted["observed_target"]
            match_type = "candidate"
            status = "pending"
            suggested_target = None
            if preferred is not None:
                match_type = "exact"
                suggested_target = preferred
                if applied:
                    status = "applied"
                    observed_target = preferred
            key = (source_term.casefold(), observed_target.casefold())
            if key in seen:
                continue
            seen.add(key)
            candidate = enqueue_candidate(
                session,
                job=job,
                tenant_id=tenant_id,
                project_id=job.project_id,
                source_term=source_term,
                observed_target=observed_target,
                suggested_target=suggested_target,
                term_type=extracted["term_type"],
                risk=classify_risk(source_term, extracted["term_type"]),
                confidence=1.0 if match_type == "exact" else 0.0,
                match_type=match_type,
                src_lang=job.provenance.get("src_lang", "en") if job.provenance else "en",
                tgt_lang=job.provenance.get("tgt_lang", "zh") if job.provenance else "zh",
                source_context=extracted["source_context"],
                target_context=extracted["target_context"],
                termbase_version=run.termbase_version,
                occurrences=extracted["occurrences"],
            )
            if candidate.status == "pending" and status == "applied":
                candidate.status = "applied"
            serialized.append(candidate_to_dict(candidate))
    return serialized


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
    candidates = _extract_candidates(
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
    record_audit(
        session,
        actor_sub=body.actor_sub,
        action="workbench.term_run.complete",
        source_sha256=job.source_sha256,
        extra={"run_id": run.id, "candidate_count": len(candidates), "status": run.status},
    )
    return {"run_id": run.id, "status": run.status, "candidates": candidates, "summary": _summary(session, run, tenant.id)}


def _summary(session: Session, run: WorkbenchTranslationRun, tenant_id: str) -> dict:
    rows = list_candidates(session, tenant_id=tenant_id, job_id=run.job_id, limit=1000)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    high_unresolved = [
        row.id
        for row in rows
        if row.risk.casefold() in _HIGH_RISK and row.status not in {"approved", "rejected"}
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
        "formal_gate": {"passed": not high_unresolved, "blocking_candidate_ids": high_unresolved},
    }


@router.get("/runs/{run_id}/term-review")
def get_term_review(run_id: str, actor_sub: str, session: Session = Depends(get_db)) -> dict:
    run, tenant, _membership = _run_for_actor(session, run_id=run_id, actor_sub=actor_sub)
    rows = list_candidates(session, tenant_id=tenant.id, job_id=run.job_id, limit=200)
    return {"summary": _summary(session, run, tenant.id), "candidates": [candidate_to_dict(row) for row in rows]}


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
    elif (high_risk or candidate.status == "pending_admin") and not is_admin:
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
        if item.action != "approve":
            raise HTTPException(status_code=400, detail="batch decisions only support approve")
        candidate = get_candidate(session, candidate_id=item.candidate_id, tenant_id=tenant.id, job_id=run.job_id)
        if candidate is None:
            raise HTTPException(status_code=404, detail="term candidate not found")
        if candidate.risk.casefold() in _HIGH_RISK or candidate.match_type not in {"exact", "alias"}:
            raise HTTPException(status_code=400, detail="candidate is not eligible for batch approval")
        decided.append(
            _decide(
                session,
                run=run,
                tenant_id=tenant.id,
                actor_sub=body.actor_sub,
                membership=membership,
                candidate_id=item.candidate_id,
                body=item,
            )
        )
    return {"count": len(decided), "decided": decided, "summary": _summary(session, run, tenant.id)}
