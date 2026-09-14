# SPDX-License-Identifier: MPL-2.0
"""PLAN-034c/d/e/f/g：/api/v1（projects / jobs / concepts / tm / qa / review / health）。"""
from __future__ import annotations

import os
import re
from typing import Any, Generator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from qyunslation.persist import repo
from qyunslation.persist.audit import record_audit, sanitize_extra
from qyunslation.persist.db import (
    DATABASE_URL_ENV,
    get_database_url,
    get_engine,
    init_engine,
    ping_db,
    reset_engine,
)
from qyunslation.persist.identity import IdentityContext, resolve_identity

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

router = APIRouter(prefix="/api/v1", tags=["API v1"])


class ProjectCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=256)


class JobCreate(BaseModel):
    project_id: str = Field(min_length=1, max_length=36)
    source_sha256: str = Field(min_length=64, max_length=64)
    storage_key: str | None = Field(default=None, max_length=512)
    attach_gateway_provenance: bool = False


def _job_dict(job) -> dict[str, Any]:
    return {
        "id": job.id,
        "project_id": job.project_id,
        "source_sha256": job.source_sha256,
        "status": job.status,
        "storage_key": job.storage_key,
        "provenance": job.provenance,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


def ensure_engine_ready() -> None:
    if get_engine() is not None:
        return
    url = get_database_url()
    if not url:
        return
    try:
        init_engine(url)
    except Exception:
        reset_engine()


def get_db() -> Generator[Session, None, None]:
    ensure_engine_ready()
    eng = get_engine()
    if eng is None:
        raise HTTPException(
            status_code=503,
            detail=f"database unavailable: set {DATABASE_URL_ENV}",
        )
    from qyunslation.persist.db import SessionLocal

    if SessionLocal is None:
        raise HTTPException(status_code=503, detail="database session factory missing")
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except HTTPException:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def require_identity(request: Request) -> IdentityContext:
    return resolve_identity(request)


def _tenant_bundle(session: Session, identity: IdentityContext):
    tenant = repo.get_or_create_tenant(session, slug=identity.tenant_slug)
    repo.ensure_membership(session, tenant_id=tenant.id, user_sub=identity.user_sub)
    return tenant


def _owned_job(session: Session, *, job_id: str, tenant_id: str):
    """Load a job only after checking the tenant-owned project boundary."""
    from qyunslation.persist.review_repo import job_owned_by_tenant

    return job_owned_by_tenant(session, job_id=job_id, tenant_id=tenant_id)


@router.get("/health")
def api_health(request: Request) -> dict[str, Any]:
    """匿名只回 schema/db；env 与配置位只对已认证身份可见。"""
    ensure_engine_ready()
    ok = ping_db()
    body: dict[str, Any] = {
        "schema": "034h",
        "db": "ok" if ok else "unavailable",
    }
    try:
        resolve_identity(request)
    except Exception:
        return body
    body["database_url_set"] = bool(get_database_url())
    body["env"] = os.environ.get("QYUNSLATION_ENV") or "development"
    return body


@router.get("/projects")
def list_projects(
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    tenant = _tenant_bundle(session, identity)
    rows = repo.list_projects(session, tenant_id=tenant.id)
    return [
        {
            "id": p.id,
            "tenant_id": p.tenant_id,
            "slug": p.slug,
            "name": p.name,
            "created_at": p.created_at.isoformat(),
        }
        for p in rows
    ]


@router.post("/projects", status_code=201)
def create_project(
    body: ProjectCreate,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    project = repo.create_project(
        session, tenant_id=tenant.id, slug=body.slug, name=body.name
    )
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="project.create",
        extra={"project_id": project.id, "slug": project.slug},
    )
    return {
        "id": project.id,
        "tenant_id": project.tenant_id,
        "slug": project.slug,
        "name": project.name,
        "created_at": project.created_at.isoformat(),
    }


@router.get("/projects/{project_id}")
def get_project(
    project_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    project = repo.get_project(session, project_id=project_id, tenant_id=tenant.id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return {
        "id": project.id,
        "tenant_id": project.tenant_id,
        "slug": project.slug,
        "name": project.name,
        "created_at": project.created_at.isoformat(),
    }


@router.get("/jobs")
def list_jobs(
    project_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    tenant = _tenant_bundle(session, identity)
    project = repo.get_project(session, project_id=project_id, tenant_id=tenant.id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    rows = repo.list_jobs(session, project_id=project.id)
    return [_job_dict(j) for j in rows]


@router.post("/jobs", status_code=201)
def create_job(
    body: JobCreate,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    digest = body.source_sha256.strip().lower()
    if not _SHA256_RE.fullmatch(digest):
        raise HTTPException(status_code=400, detail="source_sha256 must be 64 hex chars")
    tenant = _tenant_bundle(session, identity)
    project = repo.get_project(session, project_id=body.project_id, tenant_id=tenant.id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    provenance = None
    if body.attach_gateway_provenance:
        from qyunslation.gateway.config import ProfileNotWiredError, build_provenance

        try:
            provenance = build_provenance()
        except ProfileNotWiredError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    job = repo.create_job(
        session,
        project_id=project.id,
        source_sha256=digest,
        storage_key=body.storage_key,
        provenance=provenance,
    )
    # authorization 故意传入以验证审计剥离
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="job.create",
        source_sha256=digest,
        extra={"job_id": job.id, "project_id": project.id, "authorization": "REDACT_ME"},
    )
    return _job_dict(job)


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    job = repo.get_job(session, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    project = repo.get_project(session, project_id=job.project_id, tenant_id=tenant.id)
    if project is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _job_dict(job)


class ProvenanceBody(BaseModel):
    provenance: dict[str, Any] = Field(default_factory=dict)
    status: str | None = Field(default=None, max_length=32)
    # 调用方可传 api_key；服务端必须剥离
    api_key: str | None = None


@router.post("/jobs/{job_id}/provenance")
def set_job_provenance(
    job_id: str,
    body: ProvenanceBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    job = repo.get_job(session, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    project = repo.get_project(session, project_id=job.project_id, tenant_id=tenant.id)
    if project is None:
        raise HTTPException(status_code=404, detail="job not found")
    merged = dict(body.provenance or {})
    # 故意可能带入的密钥字段
    if body.api_key:
        merged["api_key"] = body.api_key
    cleaned = sanitize_extra(merged) or {}
    for bad in ("api_key", "apikey", "authorization", "password", "secret", "token"):
        cleaned.pop(bad, None)
    if "endpoint" in cleaned:
        from qyunslation.structure.model_trace import strip_endpoint

        cleaned["endpoint"] = strip_endpoint(str(cleaned["endpoint"]))
    repo.attach_provenance(session, job=job, provenance=cleaned, status=body.status)
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="job.provenance",
        source_sha256=job.source_sha256,
        extra={"job_id": job.id, "api_key": "should-strip", "keys": sorted(cleaned.keys())},
    )
    return _job_dict(job)


class ConceptCreate(BaseModel):
    preferred_source: str = Field(min_length=1, max_length=512)
    preferred_target: str = Field(min_length=1, max_length=512)
    src_lng: str = Field(default="en", max_length=16)
    tgt_lng: str = Field(default="zh", max_length=16)
    domain: str = Field(default="", max_length=64)
    layer: str = Field(default="session", max_length=32)
    evidence: str | None = None
    do_not_translate: bool = False
    # 调用方即使传 curated 也强制 staging
    status: str | None = None
    forbidden: list[dict[str, str]] = Field(default_factory=list)
    project_id: str | None = Field(default=None, max_length=36)
    term_type: str = Field(default="general", max_length=64)


@router.get("/concepts")
def list_concepts_api(
    status: str | None = None,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.concept_repo import concept_to_dict, list_concepts

    rows = list_concepts(session, status=status, tenant_id=tenant.id)
    return [concept_to_dict(c) for c in rows]


@router.post("/concepts", status_code=201)
def create_concept_api(
    body: ConceptCreate,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.concept_repo import concept_to_dict, create_staging_concept

    forbidden = [
        (str(item.get("lang") or ""), str(item.get("text") or ""))
        for item in body.forbidden
    ]
    if body.project_id and repo.get_project(
        session, project_id=body.project_id, tenant_id=tenant.id
    ) is None:
        raise HTTPException(status_code=404, detail="project not found")
    concept = create_staging_concept(
        session,
        domain=body.domain,
        layer=body.layer,
        preferred_source=body.preferred_source,
        preferred_target=body.preferred_target,
        src_lng=body.src_lng,
        tgt_lng=body.tgt_lng,
        evidence=body.evidence,
        do_not_translate=body.do_not_translate,
        forbidden=forbidden,
        tenant_id=tenant.id,
        project_id=body.project_id,
        term_type=body.term_type,
    )
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="concept.create_staging",
        extra={
            "concept_id": concept.id,
            "requested_status": body.status,
            "api_key": "should-strip",
        },
    )
    return concept_to_dict(concept)


# --- PLAN-058 术语预解析 / 译后候选闭环 ---


class TermResolveRequest(BaseModel):
    source_text: str = Field(min_length=1, max_length=20000)
    project_id: str | None = Field(default=None, max_length=36)
    src_lang: str = Field(default="en", max_length=16)
    tgt_lang: str = Field(default="zh", max_length=16)


class TermOccurrenceBody(BaseModel):
    page_no: int | None = Field(default=None, ge=1)
    block_id: str | None = Field(default=None, max_length=128)
    object_id: str | None = Field(default=None, max_length=128)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    bbox: dict[str, Any] | None = None
    source_context: str | None = Field(default=None, max_length=20000)
    target_context: str | None = Field(default=None, max_length=20000)


class TermCandidateBody(BaseModel):
    source_term: str = Field(min_length=1, max_length=512)
    observed_target: str = Field(default="", max_length=512)
    suggested_target: str | None = Field(default=None, max_length=512)
    term_type: str = Field(default="general", max_length=64)
    risk: str = Field(default="normal", max_length=32)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    match_type: str = Field(default="candidate", max_length=32)
    source_context: str | None = Field(default=None, max_length=20000)
    target_context: str | None = Field(default=None, max_length=20000)
    occurrences: list[TermOccurrenceBody] = Field(default_factory=list, max_length=1000)


class TermExtractBody(BaseModel):
    candidates: list[TermCandidateBody] = Field(min_length=1, max_length=1000)
    termbase_version: str | None = Field(default=None, max_length=128)


class TermCandidateDecisionBody(BaseModel):
    action: str = Field(min_length=1, max_length=32)
    expected_version: int = Field(ge=1)
    target_term: str | None = Field(default=None, max_length=512)
    concept_id: str | None = Field(default=None, max_length=36)
    note: str | None = Field(default=None, max_length=10000)
    scope: str = Field(default="project", max_length=32)


class TermBatchDecisionItem(TermCandidateDecisionBody):
    candidate_id: str = Field(min_length=1, max_length=36)


class TermBatchDecisionBody(BaseModel):
    decisions: list[TermBatchDecisionItem] = Field(min_length=1, max_length=200)


class TermPromoteBody(BaseModel):
    scope: str = Field(min_length=1, max_length=32)
    project_id: str | None = Field(default=None, max_length=36)
    note: str | None = Field(default=None, max_length=10000)


@router.post("/terms/resolve")
def resolve_terms_api(
    body: TermResolveRequest,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    if body.project_id and repo.get_project(
        session, project_id=body.project_id, tenant_id=tenant.id
    ) is None:
        raise HTTPException(status_code=404, detail="project not found")
    from qyunslation.glossary.termbase import (
        match_to_dict,
        resolve_runtime_terms,
        runtime_termbase_version,
    )

    matches = resolve_runtime_terms(
        session,
        tenant_id=tenant.id,
        project_id=body.project_id,
        text=body.source_text,
        src_lang=body.src_lang,
        tgt_lang=body.tgt_lang,
    )
    return {
        "matches": [match_to_dict(match) for match in matches],
        "termbase_version": runtime_termbase_version(
            session, tenant_id=tenant.id, project_id=body.project_id
        ),
        # 058c 首版只有本地确定性命中；语义候选接入后由实际路径置 true。
        "semantic_used": any(match.match_type == "semantic" for match in matches),
    }


@router.get("/terms/search")
def search_terms_api(
    source_text: str = Query(min_length=1, max_length=20000),
    project_id: str | None = Query(default=None, max_length=36),
    src_lang: str = Query(default="en", max_length=16),
    tgt_lang: str = Query(default="zh", max_length=16),
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    return resolve_terms_api(
        TermResolveRequest(
            source_text=source_text,
            project_id=project_id,
            src_lang=src_lang,
            tgt_lang=tgt_lang,
        ),
        identity,
        session,
    )


@router.post("/jobs/{job_id}/terms/extract", status_code=201)
def extract_job_terms_api(
    job_id: str,
    body: TermExtractBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    job = _owned_job(session, job_id=job_id, tenant_id=tenant.id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    from qyunslation.persist.candidate_repo import candidate_to_dict, enqueue_candidate

    created = []
    for item in body.candidates:
        candidate = enqueue_candidate(
            session,
            job=job,
            tenant_id=tenant.id,
            project_id=job.project_id,
            source_term=item.source_term,
            observed_target=item.observed_target,
            suggested_target=item.suggested_target,
            term_type=item.term_type,
            risk=item.risk,
            confidence=item.confidence,
            match_type=item.match_type,
            source_context=item.source_context,
            target_context=item.target_context,
            termbase_version=body.termbase_version,
            occurrences=[occurrence.model_dump() for occurrence in item.occurrences],
        )
        created.append(candidate_to_dict(candidate))
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="term.candidate.extract",
        source_sha256=job.source_sha256,
        extra={"job_id": job.id, "count": len(created), "api_key": "should-strip"},
    )
    return {"created": created, "count": len(created)}


@router.get("/jobs/{job_id}/terms")
def list_job_terms_api(
    job_id: str,
    status: str | None = Query(default=None, max_length=32),
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    tenant = _tenant_bundle(session, identity)
    job = _owned_job(session, job_id=job_id, tenant_id=tenant.id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    from qyunslation.persist.candidate_repo import candidate_to_dict, list_candidates

    rows = list_candidates(
        session,
        tenant_id=tenant.id,
        job_id=job.id,
        project_id=job.project_id,
        status=status,
    )
    return [candidate_to_dict(row) for row in rows]


@router.post("/jobs/{job_id}/terms/{candidate_id}/decide")
def decide_job_term_api(
    job_id: str,
    candidate_id: str,
    body: TermCandidateDecisionBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    job = _owned_job(session, job_id=job_id, tenant_id=tenant.id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    from qyunslation.persist.candidate_repo import (
        CandidateConflict,
        decide_candidate,
        get_candidate,
    )

    candidate = get_candidate(
        session, candidate_id=candidate_id, tenant_id=tenant.id, job_id=job.id
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="term candidate not found")
    try:
        result = decide_candidate(
            session,
            candidate=candidate,
            actor_sub=identity.user_sub,
            action=body.action,
            expected_version=body.expected_version,
            target_term=body.target_term,
            concept_id=body.concept_id,
            note=body.note,
            scope=body.scope,
        )
    except CandidateConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action=f"term.candidate.{body.action.strip().lower()}",
        source_sha256=job.source_sha256,
        extra={
            "job_id": job.id,
            "candidate_id": candidate.id,
            "concept_id": result.get("concept_id"),
            "api_key": "should-strip",
        },
    )
    return result


@router.post("/jobs/{job_id}/terms/batch-decide")
def batch_decide_job_terms_api(
    job_id: str,
    body: TermBatchDecisionBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    job = _owned_job(session, job_id=job_id, tenant_id=tenant.id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    from qyunslation.persist.candidate_repo import (
        CandidateConflict,
        decide_candidate,
        get_candidate,
    )

    results = []
    for item in body.decisions:
        candidate = get_candidate(
            session, candidate_id=item.candidate_id, tenant_id=tenant.id, job_id=job.id
        )
        if candidate is None:
            raise HTTPException(status_code=404, detail="term candidate not found")
        # 未知、语义或多义候选必须逐条确认，避免批量操作绕过风险控制。
        if item.action.strip().casefold() == "approve" and candidate.match_type not in {
            "exact",
            "alias",
        }:
            raise HTTPException(
                status_code=400,
                detail=f"candidate {candidate.id} is not eligible for batch approval",
            )
        try:
            results.append(
                decide_candidate(
                    session,
                    candidate=candidate,
                    actor_sub=identity.user_sub,
                    action=item.action,
                    expected_version=item.expected_version,
                    target_term=item.target_term,
                    concept_id=item.concept_id,
                    note=item.note,
                    scope=item.scope,
                )
            )
        except CandidateConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"decided": results, "count": len(results)}


@router.get("/jobs/{job_id}/term-review-summary")
def term_review_summary_api(
    job_id: str,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    job = _owned_job(session, job_id=job_id, tenant_id=tenant.id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    from qyunslation.persist.candidate_repo import list_candidates

    rows = list_candidates(
        session,
        tenant_id=tenant.id,
        job_id=job.id,
        project_id=job.project_id,
        limit=1000,
    )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    unresolved_high_risk = [
        row
        for row in rows
        if row.risk.strip().casefold() in {"high", "critical"}
        and row.status != "approved"
    ]
    return {
        "job_id": job.id,
        "total": len(rows),
        "pending": counts.get("pending", 0),
        "approved": counts.get("approved", 0),
        "rejected": counts.get("rejected", 0),
        "high_risk_unresolved": len(unresolved_high_risk),
        "formal_gate": {
            "passed": not unresolved_high_risk,
            "blocking_candidate_ids": [row.id for row in unresolved_high_risk],
        },
    }


@router.post("/concepts/{concept_id}/promote")
def promote_concept_api(
    concept_id: str,
    body: TermPromoteBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    membership = repo.ensure_membership(
        session, tenant_id=tenant.id, user_sub=identity.user_sub
    )
    if membership.role not in {"term_admin", "admin", "owner"}:
        raise HTTPException(status_code=403, detail="term_admin role required")
    from qyunslation.persist.concept_repo import concept_to_dict, get_concept

    concept = get_concept(session, concept_id)
    if concept is None or concept.tenant_id not in {None, tenant.id}:
        raise HTTPException(status_code=404, detail="concept not found")
    scope = body.scope.strip().casefold()
    if scope not in {"org", "form", "clinical", "project"}:
        raise HTTPException(status_code=400, detail="invalid promotion scope")
    if body.project_id and repo.get_project(
        session, project_id=body.project_id, tenant_id=tenant.id
    ) is None:
        raise HTTPException(status_code=404, detail="project not found")
    if scope == "project" and not body.project_id:
        raise HTTPException(status_code=400, detail="project_id is required for project scope")
    concept.status = "curated"
    concept.layer = scope
    concept.tenant_id = tenant.id
    concept.project_id = body.project_id if scope == "project" else None
    concept.evidence = (
        f"{concept.evidence or ''};promoted_by:{identity.user_sub};note:{body.note or ''}"
    )
    concept.version += 1
    session.flush()
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="concept.promote",
        extra={"concept_id": concept.id, "scope": scope, "api_key": "should-strip"},
    )
    return concept_to_dict(concept)

class TmUnitCreate(BaseModel):
    source_text: str = Field(min_length=1, max_length=20000)
    target_text: str = Field(min_length=1, max_length=20000)
    approved: bool | None = None  # true → 400；正式库只走审校 decide
    project_id: str | None = Field(default=None, max_length=36)
    src_lang: str = Field(default="en", max_length=16)
    tgt_lang: str = Field(default="zh", max_length=16)


class TmLookupRequest(BaseModel):
    source_text: str = Field(min_length=1, max_length=20000)
    project_id: str | None = Field(default=None, max_length=36)
    src_lang: str = Field(default="en", max_length=16)
    tgt_lang: str = Field(default="zh", max_length=16)
    fuzzy_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    fuzzy_limit: int = Field(default=5, ge=0, le=20)
    semantic_limit: int = Field(default=5, ge=0, le=20)


class TmImportBody(BaseModel):
    tmx: str = Field(min_length=1, max_length=8 * 1024 * 1024)
    project_id: str | None = Field(default=None, max_length=36)


@router.post("/tm/units", status_code=201)
def create_tm_unit_api(
    body: TmUnitCreate,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.tm_repo import stage_import_unit, tm_unit_to_dict

    if body.approved is True:
        raise HTTPException(
            status_code=400,
            detail="formal TM only via review decide; POST /tm/units writes staging",
        )
    if body.project_id:
        project = repo.get_project(
            session, project_id=body.project_id, tenant_id=tenant.id
        )
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
    unit = stage_import_unit(
        session,
        tenant_id=tenant.id,
        source_text=body.source_text,
        target_text=body.target_text,
        project_id=body.project_id,
        src_lang=body.src_lang,
        tgt_lang=body.tgt_lang,
    )
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="tm.unit.stage",
        extra={
            "unit_id": unit.id,
            "approved": False,
            "api_key": "should-strip",
        },
    )
    return tm_unit_to_dict(unit)


@router.post("/tm/lookup")
def tm_lookup_api(
    body: TmLookupRequest,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.tm_repo import lookup

    return lookup(
        session,
        tenant_id=tenant.id,
        source_text=body.source_text,
        src_lang=body.src_lang,
        tgt_lang=body.tgt_lang,
        project_id=body.project_id,
        fuzzy_threshold=body.fuzzy_threshold,
        fuzzy_limit=body.fuzzy_limit,
        semantic_limit=body.semantic_limit,
    )


@router.get("/tm/export.tmx")
def tm_export_tmx_api(
    src_lang: str = "en",
    tgt_lang: str = "zh",
    project_id: str | None = None,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> Response:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.tm_repo import list_approved_units
    from qyunslation.tm.tmx import build_tmx

    units = list_approved_units(
        session,
        tenant_id=tenant.id,
        src_lang=src_lang,
        tgt_lang=tgt_lang,
        project_id=project_id,
    )
    xml = build_tmx(units, src_lang=src_lang, tgt_lang=tgt_lang)
    return Response(content=xml, media_type="application/xml")


@router.post("/tm/import.tmx")
def tm_import_tmx_api(
    body: TmImportBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.tm_repo import stage_import_unit, tm_unit_to_dict
    from qyunslation.tm.tmx import parse_tmx

    try:
        parsed = parse_tmx(body.tmx)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid TMX: {exc}") from exc

    created = []
    for item in parsed:
        unit = stage_import_unit(
            session,
            tenant_id=tenant.id,
            source_text=item.source_text,
            target_text=item.target_text,
            project_id=body.project_id,
            src_lang=item.src_lang or "en",
            tgt_lang=item.tgt_lang or "zh",
        )
        created.append(tm_unit_to_dict(unit))
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="tm.tmx.import",
        extra={"count": len(created), "api_key": "should-strip"},
    )
    return {"imported": len(created), "units": created, "note": "imported as approved=false"}


class QaRunBody(BaseModel):
    source_text: str = Field(min_length=1)
    target_text: str = ""
    role: str = "body"
    domain: str = ""
    forbidden: list[str] = Field(default_factory=list)
    table_qc_codes: list[str] = Field(default_factory=list)
    page_qc_codes: list[str] = Field(default_factory=list)
    enable_repair: bool = False
    enable_review: bool = False
    job_id: str | None = Field(default=None, max_length=36)
    # 测试用：传入则跳过真实 provider，用该字符串作为 repair 结果
    mock_repaired_text: str | None = None


@router.post("/qa/run")
def qa_run_api(
    body: QaRunBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    job = None
    if body.job_id:
        from qyunslation.persist.review_repo import job_owned_by_tenant

        job = job_owned_by_tenant(session, job_id=body.job_id, tenant_id=tenant.id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
    from qyunslation.gateway.pipeline import run_segment_pipeline

    provider = None
    if body.mock_repaired_text is not None:

        class _Mock:
            def translate(self, source: str, *, system: str | None = None) -> str:
                return body.target_text or source

            def review(self, source: str, target: str, *, findings: list[str] | None = None) -> str:
                return "PASS"

            def repair(self, source: str, target: str, *, findings: list[str] | None = None) -> str:
                return body.mock_repaired_text or target

        provider = _Mock()
    elif body.enable_repair or body.enable_review:
        try:
            from qyunslation.gateway.provider import get_provider

            provider = get_provider()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"provider unavailable: {exc}") from exc

    out = run_segment_pipeline(
        body.source_text,
        target=body.target_text,
        role=body.role,
        domain=body.domain,
        forbidden=body.forbidden or None,
        table_qc_codes=body.table_qc_codes or None,
        page_qc_codes=body.page_qc_codes or None,
        provider=provider,
        enable_review=body.enable_review,
        enable_repair=body.enable_repair,
    )
    if job is not None and out.get("qa", {}).get("blocked"):
        repo.attach_provenance(
            session,
            job=job,
            provenance=job.provenance or {"qa_blocked": True},
            status="qa_blocked",
        )
        out["job_status"] = "qa_blocked"
        out["job_id"] = job.id
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="qa.run",
        extra={
            "blocked": out.get("qa", {}).get("blocked"),
            "repaired": out.get("repaired"),
            "api_key": "should-strip",
        },
    )
    return out


class ReviewEnqueueItem(BaseModel):
    # 上限对齐 ORM 列宽，避免超长值到 PG 才报 500
    source_text: str = Field(min_length=1, max_length=20000)
    machine_text: str = Field(default="", max_length=20000)
    block_id: str | None = Field(default=None, max_length=128)
    policy: str = Field(default="TRANSLATE", max_length=32)
    role: str = Field(default="body", max_length=64)


class ReviewEnqueueBody(BaseModel):
    job_id: str = Field(min_length=1, max_length=36)
    segments: list[ReviewEnqueueItem] = Field(min_length=1, max_length=500)


class ReviewNoteBody(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


class ReviewDecideBody(BaseModel):
    action: str = Field(min_length=1, max_length=16)  # approve | reject
    revised_text: str | None = Field(default=None, max_length=20000)
    promote_term: bool = False
    src_lang: str = Field(default="en", max_length=16)
    tgt_lang: str = Field(default="zh", max_length=16)


@router.post("/review/enqueue")
def review_enqueue_api(
    body: ReviewEnqueueBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.review_repo import (
        enqueue_segments,
        job_owned_by_tenant,
        segment_to_dict,
    )

    job = job_owned_by_tenant(session, job_id=body.job_id, tenant_id=tenant.id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    items = [s.model_dump() for s in body.segments]
    created, skipped = enqueue_segments(session, job=job, items=items)
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="review.enqueue",
        source_sha256=job.source_sha256,
        extra={
            "job_id": job.id,
            "created": len(created),
            "skipped": len(skipped),
            "api_key": "should-strip",
        },
    )
    return {
        "created": [segment_to_dict(s) for s in created],
        "skipped": skipped,
        "count": len(created),
    }


@router.get("/review/queue")
def review_queue_api(
    job_id: str | None = None,
    status: str | None = None,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.review_repo import list_queue, segment_to_dict

    rows = list_queue(session, tenant_id=tenant.id, job_id=job_id, status=status)
    return [segment_to_dict(s) for s in rows]


@router.post("/review/segments/{segment_id}/note", status_code=201)
def review_note_api(
    segment_id: str,
    body: ReviewNoteBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.review_repo import add_note, get_segment_for_tenant

    seg = get_segment_for_tenant(session, segment_id=segment_id, tenant_id=tenant.id)
    if seg is None:
        raise HTTPException(status_code=404, detail="segment not found")
    note = add_note(
        session, segment=seg, author_sub=identity.user_sub, body=body.body
    )
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="review.segment.note",
        source_sha256=seg.source_sha256,
        extra={"segment_id": seg.id, "api_key": "should-strip"},
    )
    return {
        "id": note.id,
        "segment_id": seg.id,
        "author_sub": note.author_sub,
        "body": note.body,
        "created_at": note.created_at.isoformat(),
    }


@router.post("/review/segments/{segment_id}/decide")
def review_decide_api(
    segment_id: str,
    body: ReviewDecideBody,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.review_repo import (
        ReviewError,
        decide_segment,
        get_segment_for_tenant,
        job_owned_by_tenant,
    )

    seg = get_segment_for_tenant(session, segment_id=segment_id, tenant_id=tenant.id)
    if seg is None:
        raise HTTPException(status_code=404, detail="segment not found")
    job = job_owned_by_tenant(session, job_id=seg.job_id, tenant_id=tenant.id)
    project_id = job.project_id if job else None
    try:
        result = decide_segment(
            session,
            segment=seg,
            tenant_id=tenant.id,
            actor_sub=identity.user_sub,
            action=body.action,
            revised_text=body.revised_text,
            promote_term=body.promote_term,
            project_id=project_id,
            src_lang=body.src_lang,
            tgt_lang=body.tgt_lang,
        )
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    action = body.action.strip().lower()
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action=f"review.segment.{action}",
        source_sha256=seg.source_sha256,
        extra={
            "segment_id": seg.id,
            "tm_unit_id": result.get("tm_unit_id"),
            "concept_id": result.get("concept_id"),
            "api_key": "should-strip",
        },
    )
    return result


@router.get("/review/diff")
def review_diff_api(
    source_sha256: str | None = None,
    segment_id: str | None = None,
    version_a: int | None = None,
    version_b: int | None = None,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.review_repo import ReviewError, diff_revisions

    if not source_sha256 and not segment_id:
        raise HTTPException(status_code=400, detail="source_sha256 or segment_id required")
    try:
        return diff_revisions(
            session,
            tenant_id=tenant.id,
            source_sha256=source_sha256.lower() if source_sha256 else None,
            segment_id=segment_id,
            version_a=version_a,
            version_b=version_b,
        )
    except ReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/review/suggestions")
def review_suggestions_api(
    source_text: str = Query(min_length=1, max_length=20000),
    target_text: str | None = Query(default=None, max_length=20000),
    project_id: str | None = Query(default=None, max_length=36),
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.concept_repo import list_forbidden_texts
    from qyunslation.persist.review_repo import suggestions

    if not (source_text or "").strip():
        raise HTTPException(status_code=400, detail="source_text required")
    forbidden = list_forbidden_texts(session, curated_only=True)
    return suggestions(
        session,
        tenant_id=tenant.id,
        source_text=source_text,
        target_text=target_text,
        project_id=project_id,
        forbidden=forbidden,
    )
