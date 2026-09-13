# SPDX-License-Identifier: MPL-2.0
"""PLAN-034c：租户 / 项目 / job 仓储。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from qyunslation.persist.models import Job, Project, Tenant, UserMembership


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
) -> Job:
    job = Job(
        project_id=project_id,
        source_sha256=source_sha256.lower(),
        storage_key=storage_key,
        status=status,
    )
    session.add(job)
    session.flush()
    return job


def get_job(session: Session, *, job_id: str) -> Job | None:
    return session.get(Job, job_id)
