# SPDX-License-Identifier: MPL-2.0
"""PLAN-034c–g：租户 / 项目 / job / 审计 + Concept + TM + Review ORM。"""
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

try:  # Optional at import time so SQLite unit tests stay lightweight.
    from pgvector.sqlalchemy import Vector as PgVector
except ImportError:  # pragma: no cover - exercised only before optional install
    PgVector = None

from sqlalchemy.types import TypeDecorator


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class EmbeddingVector(TypeDecorator):
    """Use pgvector in PostgreSQL and JSON for portable test databases."""

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int = 1024, **kwargs):
        self.dim = int(dim)
        super().__init__(**kwargs)

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql" and PgVector is not None:
            return dialect.type_descriptor(PgVector(self.dim))
        return dialect.type_descriptor(JSON())


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
    # PLAN-034f：模型/术语/TM/算法溯源（无 API Key）
    provenance: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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
    __table_args__ = (
        Index("ix_concept_status_layer", "status", "layer"),
        Index("ix_concept_runtime_scope", "tenant_id", "project_id", "status", "layer"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    domain: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="staging")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    license: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    do_not_translate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    layer: Mapped[str] = mapped_column(String(32), nullable=False, default="clinical")
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("project.id", ondelete="CASCADE"), nullable=True
    )
    term_type: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    authority: Mapped[str | None] = mapped_column(String(256), nullable=True)
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
        Index("ix_concept_term_normalized", "normalized_text"),
        UniqueConstraint("concept_id", "lang", "role", "text", name="uq_concept_term"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concept.id", ondelete="CASCADE"), nullable=False
    )
    lang: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_text: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="preferred")

    concept: Mapped[Concept] = relationship(back_populates="terms")


class ConceptTermEmbedding(Base):
    """PLAN-058：ConceptTerm 向量；PostgreSQL 使用 pgvector，SQLite 使用 JSON。"""

    __tablename__ = "concept_term_embedding"
    __table_args__ = (Index("ix_concept_term_embedding_model", "model"),)

    term_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concept_term.id", ondelete="CASCADE"), primary_key=True
    )
    dim: Mapped[int] = mapped_column(Integer, nullable=False, default=1024)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    vector: Mapped[list] = mapped_column(EmbeddingVector(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


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


class TmUnit(Base):
    """批准驱动的翻译记忆句段（与 concept 分表）。"""

    __tablename__ = "tm_unit"
    __table_args__ = (
        Index(
            "ix_tm_unit_lookup",
            "tenant_id",
            "src_lang",
            "tgt_lang",
            "source_norm",
            "placeholder_sig",
        ),
        Index("ix_tm_unit_tenant_approved", "tenant_id", "approved"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("project.id", ondelete="SET NULL"), nullable=True
    )
    src_lang: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    tgt_lang: Mapped[str] = mapped_column(String(16), nullable=False, default="zh")
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    target_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_norm: Mapped[str] = mapped_column(Text, nullable=False, default="")
    placeholder_sig: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class TmUnitEmbedding(Base):
    """PLAN-055：tm_unit 旁路向量（JSON，非 pgvector）。"""

    __tablename__ = "tm_unit_embedding"

    unit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tm_unit.id", ondelete="CASCADE"), primary_key=True
    )
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    vector: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


# --- PLAN-034g 人工审校 ---


class ReviewSegment(Base):
    """job 下待审句段；原始 source_sha256 只读引用。"""

    __tablename__ = "review_segment"
    __table_args__ = (
        Index("ix_review_segment_job_status", "job_id", "status"),
        Index("ix_review_segment_source_sha", "source_sha256"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("job.id", ondelete="CASCADE"), nullable=False
    )
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    block_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    policy: Mapped[str] = mapped_column(String(32), nullable=False, default="TRANSLATE")
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="body")
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    machine_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    revised_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    decided_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    notes: Mapped[list["ReviewNote"]] = relationship(
        back_populates="segment", cascade="all, delete-orphan"
    )
    revisions: Mapped[list["ReviewRevision"]] = relationship(
        back_populates="segment", cascade="all, delete-orphan"
    )


class ReviewNote(Base):
    __tablename__ = "review_note"
    __table_args__ = (Index("ix_review_note_segment", "segment_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    segment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("review_segment.id", ondelete="CASCADE"), nullable=False
    )
    author_sub: Mapped[str] = mapped_column(String(256), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    segment: Mapped[ReviewSegment] = relationship(back_populates="notes")


class ReviewRevision(Base):
    """每次批准/修订递增 version，供 diff。"""

    __tablename__ = "review_revision"
    __table_args__ = (
        UniqueConstraint("segment_id", "version", name="uq_review_revision_seg_ver"),
        Index("ix_review_revision_source_sha", "source_sha256"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    segment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("review_segment.id", ondelete="CASCADE"), nullable=False
    )
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    target_text: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False, default="revise")
    actor_sub: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    segment: Mapped[ReviewSegment] = relationship(back_populates="revisions")


# --- PLAN-058 译后术语候选与人工决策 ---


class DocumentTermCandidate(Base):
    """一个翻译任务中的术语候选；正式词库只接受人工决策结果。"""

    __tablename__ = "document_term_candidate"
    __table_args__ = (
        Index("ix_document_term_candidate_job_status", "job_id", "status"),
        Index("ix_document_term_candidate_project_source", "project_id", "source_norm"),
        UniqueConstraint(
            "job_id", "source_norm", "observed_target", name="uq_document_term_candidate"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("job.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project.id", ondelete="CASCADE"), nullable=False
    )
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    src_lang: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    tgt_lang: Mapped[str] = mapped_column(String(16), nullable=False, default="zh")
    source_term: Mapped[str] = mapped_column(String(512), nullable=False)
    source_norm: Mapped[str] = mapped_column(String(512), nullable=False)
    observed_target: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    suggested_target: Mapped[str | None] = mapped_column(String(512), nullable=True)
    term_type: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    risk: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    match_type: Mapped[str] = mapped_column(String(32), nullable=False, default="candidate")
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    concept_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("concept.id", ondelete="SET NULL"), nullable=True
    )
    termbase_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    occurrences: Mapped[list[DocumentTermOccurrence]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )
    decisions: Mapped[list[TermDecision]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )


class DocumentTermOccurrence(Base):
    __tablename__ = "document_term_occurrence"
    __table_args__ = (Index("ix_document_term_occurrence_candidate", "candidate_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document_term_candidate.id", ondelete="CASCADE"), nullable=False
    )
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    block_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    object_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    candidate: Mapped[DocumentTermCandidate] = relationship(back_populates="occurrences")


class TermDecision(Base):
    __tablename__ = "term_decision"
    __table_args__ = (Index("ix_term_decision_candidate", "candidate_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document_term_candidate.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_sub: Mapped[str] = mapped_column(String(256), nullable=False)
    source_term: Mapped[str] = mapped_column(String(512), nullable=False)
    target_term: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    concept_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("concept.id", ondelete="SET NULL"), nullable=True
    )
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="project")
    from_version: Mapped[int] = mapped_column(Integer, nullable=False)
    to_version: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    candidate: Mapped[DocumentTermCandidate] = relationship(back_populates="decisions")
