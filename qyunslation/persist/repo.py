# SPDX-License-Identifier: MPL-2.0
"""PLAN-034c：租户 / 项目 / job 仓储。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from qyunslation.persist.models import Job, Project, Tenant, UserMembership


COMPANY_TERMBASE_PROJECT_SLUG = "company-termbase"
COMPANY_TERMBASE_PROJECT_NAME = "公司共享专业词库"


def get_or_create_tenant(session: Session, *, slug: str, name: str | None = None) -> Tenant:
    row = session.scalar(select(Tenant).where(Tenant.slug == slug))
    if row is not None:
        return row
    row = Tenant(slug=slug, name=name or slug)
    session.add(row)
    session.flush()
    return row


def ensure_membership(
    session: Session, *, tenant_id: str, user_sub: str, role: str = "member"
) -> UserMembership:
    row = session.scalar(
        select(UserMembership).where(
            UserMembership.tenant_id == tenant_id,
            UserMembership.user_sub == user_sub,
        )
    )
    if row is not None:
        return row
    row = UserMembership(tenant_id=tenant_id, user_sub=user_sub, role=role)
    session.add(row)
    session.flush()
    return row


def list_projects(session: Session, *, tenant_id: str) -> list[Project]:
    return list(
        session.scalars(select(Project).where(Project.tenant_id == tenant_id).order_by(Project.created_at))
    )


def create_project(
    session: Session, *, tenant_id: str, slug: str, name: str
) -> Project:
    project = Project(tenant_id=tenant_id, slug=slug, name=name)
    session.add(project)
    session.flush()
    return project


def get_or_create_company_termbase_project(session: Session, *, tenant_id: str) -> Project:
    """Return the tenant-local project used by the Gradio shared termbase.

    A Project remains mandatory for Jobs and Concepts.  A stable hidden project
    preserves that invariant without making the workbench accept a client
    supplied project id or creating a cross-tenant global dictionary.
    """
    existing = session.scalar(
        select(Project).where(
            Project.tenant_id == tenant_id,
            Project.slug == COMPANY_TERMBASE_PROJECT_SLUG,
        )
    )
    if existing is not None:
        return existing
    return create_project(
        session,
        tenant_id=tenant_id,
        slug=COMPANY_TERMBASE_PROJECT_SLUG,
        name=COMPANY_TERMBASE_PROJECT_NAME,
    )


def get_project(session: Session, *, project_id: str, tenant_id: str) -> Project | None:
    return session.scalar(
        select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id)
    )


def list_jobs(session: Session, *, project_id: str) -> list[Job]:
    return list(
        session.scalars(select(Job).where(Job.project_id == project_id).order_by(Job.created_at))
    )


def create_job(
    session: Session,
    *,
    project_id: str,
    source_sha256: str,
    storage_key: str | None = None,
    status: str = "pending",
    provenance: dict | None = None,
) -> Job:
    job = Job(
        project_id=project_id,
        source_sha256=source_sha256.lower(),
        storage_key=storage_key,
        status=status,
        provenance=provenance,
    )
    session.add(job)
    session.flush()
    return job


def attach_provenance(
    session: Session,
    *,
    job: Job,
    provenance: dict,
    status: str | None = None,
) -> Job:
    """写入去密钥 provenance；可选更新 status（如 qa_blocked）。"""
    from qyunslation.persist.audit import sanitize_extra

    cleaned = sanitize_extra(dict(provenance)) or {}
    # sanitize_extra 会丢掉密钥键；再强制禁止
    for bad in ("api_key", "apikey", "authorization", "password", "secret", "token"):
        cleaned.pop(bad, None)
    job.provenance = cleaned
    if status is not None:
        job.status = status
    session.flush()
    return job


def get_job(session: Session, *, job_id: str) -> Job | None:
    return session.get(Job, job_id)
