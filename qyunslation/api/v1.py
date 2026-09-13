# SPDX-License-Identifier: MPL-2.0
"""PLAN-034c：/api/v1 骨架（projects / jobs / health）。"""
from __future__ import annotations

import os
import re
from typing import Any, Generator

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from qyunslation.persist import repo
from qyunslation.persist.audit import record_audit
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
        "schema": "034c",
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
    return [
        {
            "id": j.id,
            "project_id": j.project_id,
            "source_sha256": j.source_sha256,
            "status": j.status,
            "storage_key": j.storage_key,
            "created_at": j.created_at.isoformat(),
            "updated_at": j.updated_at.isoformat(),
        }
        for j in rows
    ]


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
    job = repo.create_job(
        session,
        project_id=project.id,
        source_sha256=digest,
        storage_key=body.storage_key,
    )
    # authorization 故意传入以验证审计剥离
    record_audit(
        session,
        actor_sub=identity.user_sub,
        action="job.create",
        source_sha256=digest,
        extra={"job_id": job.id, "project_id": project.id, "authorization": "REDACT_ME"},
    )
    return {
        "id": job.id,
        "project_id": job.project_id,
        "source_sha256": job.source_sha256,
        "status": job.status,
        "storage_key": job.storage_key,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


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
    return {
        "id": job.id,
        "project_id": job.project_id,
        "source_sha256": job.source_sha256,
        "status": job.status,
        "storage_key": job.storage_key,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }
