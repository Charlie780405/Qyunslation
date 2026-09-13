# SPDX-License-Identifier: MPL-2.0
"""PLAN-034c/d/e/f/g：/api/v1（projects / jobs / concepts / tm / qa / review / health）。"""
from __future__ import annotations

import os
import re
from typing import Any, Generator

from fastapi import APIRouter, Depends, HTTPException, Request, Response
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


@router.get("/health")
def api_health() -> dict[str, Any]:
    ensure_engine_ready()
    ok = ping_db()
    return {
        "schema": "034h",
        "db": "ok" if ok else "unavailable",
        "database_url_set": bool(get_database_url()),
        "env": (os.environ.get("QYUNSLATION_ENV") or "development"),
    }


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


@router.get("/concepts")
def list_concepts_api(
    status: str | None = None,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    _tenant_bundle(session, identity)
    from qyunslation.persist.concept_repo import concept_to_dict, list_concepts

    rows = list_concepts(session, status=status)
    return [concept_to_dict(c) for c in rows]


@router.post("/concepts", status_code=201)
def create_concept_api(
    body: ConceptCreate,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    _tenant_bundle(session, identity)
    from qyunslation.persist.concept_repo import concept_to_dict, create_staging_concept

    forbidden = [
        (str(item.get("lang") or ""), str(item.get("text") or ""))
        for item in body.forbidden
    ]
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


class TmUnitCreate(BaseModel):
    source_text: str = Field(min_length=1)
    target_text: str = Field(min_length=1)
    approved: bool | None = None  # 缺省或 false → 400
    project_id: str | None = Field(default=None, max_length=36)
    src_lang: str = Field(default="en", max_length=16)
    tgt_lang: str = Field(default="zh", max_length=16)


class TmLookupRequest(BaseModel):
    source_text: str = Field(min_length=1)
    project_id: str | None = Field(default=None, max_length=36)
    src_lang: str = Field(default="en", max_length=16)
    tgt_lang: str = Field(default="zh", max_length=16)
    fuzzy_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    fuzzy_limit: int = Field(default=5, ge=0, le=20)


class TmImportBody(BaseModel):
    tmx: str = Field(min_length=1)
    project_id: str | None = Field(default=None, max_length=36)


@router.post("/tm/units", status_code=201)
def create_tm_unit_api(
    body: TmUnitCreate,
    identity: IdentityContext = Depends(require_identity),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    tenant = _tenant_bundle(session, identity)
    from qyunslation.persist.tm_repo import (
        ApprovalRequiredError,
        create_approved_unit,
        tm_unit_to_dict,
    )

    if body.approved is not True:
        raise HTTPException(
            status_code=400,
            detail="approved=true required to enter formal TM (simulate 034g approval)",
        )
    try:
        unit = create_approved_unit(
            session,
            tenant_id=tenant.id,
            source_text=body.source_text,
            target_text=body.target_text,
            approved=True,
            approved_by=identity.user_sub,
            project_id=body.project_id,
            src_lang=body.src_lang,
            tgt_lang=body.tgt_lang,
        )
    except ApprovalRequiredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="tm.unit.create",
        extra={
            "unit_id": unit.id,
            "approved": True,
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
        from xml.etree.ElementTree import ParseError

        if isinstance(exc, ParseError):
            raise HTTPException(status_code=400, detail=f"invalid TMX: {exc}") from exc
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
    _tenant_bundle(session, identity)
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
    if body.job_id and out.get("qa", {}).get("blocked"):
        job = repo.get_job(session, job_id=body.job_id)
        if job is not None:
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
    source_text: str = Field(min_length=1)
    machine_text: str = ""
    block_id: str | None = None
    policy: str = "TRANSLATE"
    role: str = "body"


class ReviewEnqueueBody(BaseModel):
    job_id: str = Field(min_length=1, max_length=36)
    segments: list[ReviewEnqueueItem] = Field(min_length=1)


class ReviewNoteBody(BaseModel):
    body: str = Field(min_length=1)


class ReviewDecideBody(BaseModel):
    action: str = Field(min_length=1)  # approve | reject
    revised_text: str | None = None
    promote_term: bool = False
    src_lang: str = "en"
    tgt_lang: str = "zh"


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
    source_text: str,
    target_text: str | None = None,
    project_id: str | None = None,
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

