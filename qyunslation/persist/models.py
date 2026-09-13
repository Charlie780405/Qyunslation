# SPDX-License-Identifier: MPL-2.0
"""PLAN-034c/d：租户 / 项目 / 成员 / job / 审计 + Concept 术语 ORM。

TM 表留给 034e。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenant"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    projects: Mapped[list[Project]] = relationship(back_populates="tenant")
    memberships: Mapped[list[UserMembership]] = relationship(back_populates="tenant")


class Project(Base):
    __tablename__ = "project"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_project_tenant_slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    tenant: Mapped[Tenant] = relationship(back_populates="projects")
    jobs: Mapped[list[Job]] = relationship(back_populates="project")


class UserMembership(Base):
    __tablename__ = "user_membership"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_sub", name="uq_membership_tenant_user"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    user_sub: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="member")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    tenant: Mapped[Tenant] = relationship(back_populates="memberships")


class Job(Base):
    __tablename__ = "job"
    __table_args__ = (Index("ix_job_source_sha256", "source_sha256"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="jobs")


class AuditEvent(Base):
    __tablename__ = "audit_event"
    __table_args__ = (Index("ix_audit_event_created_at", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_sub: Mapped[str] = mapped_column(String(256), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


# --- PLAN-034d Concept 术语库 ---


class Concept(Base):
    __tablename__ = "concept"
    __table_args__ = (Index("ix_concept_status_layer", "status", "layer"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    domain: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="staging")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    license: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    do_not_translate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    layer: Mapped[str] = mapped_column(String(32), nullable=False, default="clinical")
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenant.id", ondelete="SET NULL"), nullable=True
    )
    # 幂等导入键：normalize(source)|layer|lang_pair 指纹
    import_key: Mapped[str | None] = mapped_column(String(512), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    terms: Mapped[list[ConceptTerm]] = relationship(
        back_populates="concept", cascade="all, delete-orphan"
    )
    forbiddens: Mapped[list[ConceptForbidden]] = relationship(
        back_populates="concept", cascade="all, delete-orphan"
    )


class ConceptTerm(Base):
    __tablename__ = "concept_term"
    __table_args__ = (
        Index("ix_concept_term_text", "text"),
        UniqueConstraint("concept_id", "lang", "role", "text", name="uq_concept_term"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concept.id", ondelete="CASCADE"), nullable=False
    )
    lang: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="preferred")

    concept: Mapped[Concept] = relationship(back_populates="terms")


class ConceptForbidden(Base):
    __tablename__ = "concept_forbidden"
    __table_args__ = (
        UniqueConstraint("concept_id", "lang", "text", name="uq_concept_forbidden"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concept.id", ondelete="CASCADE"), nullable=False
    )
    lang: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    text: Mapped[str] = mapped_column(String(512), nullable=False)

    concept: Mapped[Concept] = relationship(back_populates="forbiddens")
