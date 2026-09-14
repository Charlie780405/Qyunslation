# SPDX-License-Identifier: MPL-2.0
"""PLAN-058：项目术语闭环、候选审校与 ConceptTerm 向量旁路表。

Revision ID: 058a0001
Revises: 055a0001
Create Date: 2026-09-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover - migration requires pgvector in production
    Vector = None


revision: str = "058a0001"
down_revision: Union[str, None] = "055a0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _vector_type():
    return Vector(1024) if Vector is not None else sa.JSON()


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    concept_columns = [
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("term_type", sa.String(64), nullable=False, server_default="general"),
        sa.Column("definition", sa.Text(), nullable=True),
        sa.Column("authority", sa.String(256), nullable=True),
    ]
    if is_postgres:
        for column in concept_columns:
            op.add_column("concept", column)
        op.create_foreign_key(
            "fk_concept_project_id",
            "concept",
            "project",
            ["project_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(
            "ix_concept_runtime_scope",
            "concept",
            ["tenant_id", "project_id", "status", "layer"],
        )
    else:
        # SQLite cannot ALTER TABLE ADD CONSTRAINT; batch mode rebuilds the
        # table while preserving existing rows and the new FK.
        with op.batch_alter_table("concept", recreate="always") as batch:
            for column in concept_columns:
                batch.add_column(column)
            batch.create_foreign_key(
                "fk_concept_project_id",
                "project",
                ["project_id"],
                ["id"],
                ondelete="CASCADE",
            )
            batch.create_index(
                "ix_concept_runtime_scope",
                ["tenant_id", "project_id", "status", "layer"],
            )

    op.add_column(
        "concept_term",
        sa.Column("normalized_text", sa.String(512), nullable=True),
    )
    op.execute("UPDATE concept_term SET normalized_text = lower(trim(text))")
    if is_postgres:
        op.alter_column("concept_term", "normalized_text", nullable=False)
        op.create_index("ix_concept_term_normalized", "concept_term", ["normalized_text"])
    else:
        with op.batch_alter_table("concept_term", recreate="always") as batch:
            batch.alter_column("normalized_text", nullable=False)
            batch.create_index("ix_concept_term_normalized", ["normalized_text"])

    op.create_table(
        "concept_term_embedding",
        sa.Column("term_id", sa.String(36), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False, server_default="1024"),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("vector", _vector_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["term_id"], ["concept_term.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("term_id"),
    )
    op.create_index(
        "ix_concept_term_embedding_model",
        "concept_term_embedding",
        ["model"],
    )
    if is_postgres and Vector is not None:
        op.create_index(
            "ix_concept_term_embedding_vector_hnsw",
            "concept_term_embedding",
            ["vector"],
            unique=False,
            postgresql_using="hnsw",
            postgresql_ops={"vector": "vector_cosine_ops"},
        )

    op.create_table(
        "document_term_candidate",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("job_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("src_lang", sa.String(16), nullable=False),
        sa.Column("tgt_lang", sa.String(16), nullable=False),
        sa.Column("source_term", sa.String(512), nullable=False),
        sa.Column("source_norm", sa.String(512), nullable=False),
        sa.Column("observed_target", sa.String(512), nullable=False),
        sa.Column("suggested_target", sa.String(512), nullable=True),
        sa.Column("term_type", sa.String(64), nullable=False),
        sa.Column("risk", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("match_type", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("concept_id", sa.String(36), nullable=True),
        sa.Column("termbase_version", sa.String(128), nullable=True),
        sa.Column("source_context", sa.Text(), nullable=True),
        sa.Column("target_context", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.String(256), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["job.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["concept_id"], ["concept.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id", "source_norm", "observed_target", name="uq_document_term_candidate"
        ),
    )
    op.create_index(
        "ix_document_term_candidate_job_status",
        "document_term_candidate",
        ["job_id", "status"],
    )
    op.create_index(
        "ix_document_term_candidate_project_source",
        "document_term_candidate",
        ["project_id", "source_norm"],
    )

    op.create_table(
        "document_term_occurrence",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("candidate_id", sa.String(36), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column("block_id", sa.String(128), nullable=True),
        sa.Column("object_id", sa.String(128), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("bbox", sa.JSON(), nullable=True),
        sa.Column("source_context", sa.Text(), nullable=True),
        sa.Column("target_context", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["document_term_candidate.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_term_occurrence_candidate",
        "document_term_occurrence",
        ["candidate_id"],
    )

    op.create_table(
        "term_decision",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("candidate_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("actor_sub", sa.String(256), nullable=False),
        sa.Column("source_term", sa.String(512), nullable=False),
        sa.Column("target_term", sa.String(512), nullable=False),
        sa.Column("concept_id", sa.String(36), nullable=True),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("from_version", sa.Integer(), nullable=False),
        sa.Column("to_version", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["document_term_candidate.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["concept_id"], ["concept.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_term_decision_candidate", "term_decision", ["candidate_id"])


def downgrade() -> None:
    op.drop_index("ix_term_decision_candidate", table_name="term_decision")
    op.drop_table("term_decision")
    op.drop_index(
        "ix_document_term_occurrence_candidate", table_name="document_term_occurrence"
    )
    op.drop_table("document_term_occurrence")
    op.drop_index(
        "ix_document_term_candidate_project_source", table_name="document_term_candidate"
    )
    op.drop_index(
        "ix_document_term_candidate_job_status", table_name="document_term_candidate"
    )
    op.drop_table("document_term_candidate")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_index(
            "ix_concept_term_embedding_vector_hnsw", table_name="concept_term_embedding"
        )
    op.drop_index("ix_concept_term_embedding_model", table_name="concept_term_embedding")
    op.drop_table("concept_term_embedding")
    op.drop_index("ix_concept_term_normalized", table_name="concept_term")
    op.drop_column("concept_term", "normalized_text")
    op.drop_index("ix_concept_runtime_scope", table_name="concept")
    op.drop_constraint("fk_concept_project_id", "concept", type_="foreignkey")
    op.drop_column("concept", "authority")
    op.drop_column("concept", "definition")
    op.drop_column("concept", "term_type")
    op.drop_column("concept", "project_id")
