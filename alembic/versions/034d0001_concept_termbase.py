# SPDX-License-Identifier: MPL-2.0
"""PLAN-034d：concept 三表 Alembic 迁移。

Revision ID: 034d0001
Revises: 034c0001
Create Date: 2026-09-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "034d0001"
down_revision: Union[str, None] = "034c0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "concept",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("license", sa.String(length=128), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("do_not_translate", sa.Boolean(), nullable=False),
        sa.Column("layer", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("import_key", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("import_key"),
    )
    op.create_index("ix_concept_status_layer", "concept", ["status", "layer"])
    op.create_table(
        "concept_term",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("concept_id", sa.String(length=36), nullable=False),
        sa.Column("lang", sa.String(length=16), nullable=False),
        sa.Column("text", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["concept_id"], ["concept.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("concept_id", "lang", "role", "text", name="uq_concept_term"),
    )
    op.create_index("ix_concept_term_text", "concept_term", ["text"])
    op.create_table(
        "concept_forbidden",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("concept_id", sa.String(length=36), nullable=False),
        sa.Column("lang", sa.String(length=16), nullable=False),
        sa.Column("text", sa.String(length=512), nullable=False),
        sa.ForeignKeyConstraint(["concept_id"], ["concept.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("concept_id", "lang", "text", name="uq_concept_forbidden"),
    )


def downgrade() -> None:
    op.drop_table("concept_forbidden")
    op.drop_index("ix_concept_term_text", table_name="concept_term")
    op.drop_table("concept_term")
    op.drop_index("ix_concept_status_layer", table_name="concept")
    op.drop_table("concept")
