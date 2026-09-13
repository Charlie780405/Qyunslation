# SPDX-License-Identifier: MPL-2.0
"""PLAN-034e：tm_unit Alembic 迁移。

Revision ID: 034e0001
Revises: 034d0001
Create Date: 2026-09-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "034e0001"
down_revision: Union[str, None] = "034d0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tm_unit",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("src_lang", sa.String(length=16), nullable=False),
        sa.Column("tgt_lang", sa.String(length=16), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("target_text", sa.Text(), nullable=False),
        sa.Column("source_norm", sa.Text(), nullable=False),
        sa.Column("placeholder_sig", sa.String(length=512), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("approved_by", sa.String(length=256), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tm_unit_lookup",
        "tm_unit",
        ["tenant_id", "src_lang", "tgt_lang", "source_norm", "placeholder_sig"],
    )
    op.create_index(
        "ix_tm_unit_tenant_approved",
        "tm_unit",
        ["tenant_id", "approved"],
    )


def downgrade() -> None:
    op.drop_index("ix_tm_unit_tenant_approved", table_name="tm_unit")
    op.drop_index("ix_tm_unit_lookup", table_name="tm_unit")
    op.drop_table("tm_unit")
