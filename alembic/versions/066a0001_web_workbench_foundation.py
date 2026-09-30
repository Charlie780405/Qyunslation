# SPDX-License-Identifier: MPL-2.0
"""PLAN-066a: web workbench preferences and upload preflight records.

Revision ID: 066a0001
Revises: 063a0001
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "066a0001"
down_revision: Union[str, None] = "063a0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "web_preference",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("user_sub", sa.String(length=256), nullable=False),
        sa.Column("preferences", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_sub", name="uq_web_preference_tenant_user"),
    )
    op.create_index("ix_web_preference_tenant_user", "web_preference", ["tenant_id", "user_sub"])
    op.create_table(
        "preflight_record",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("actor_sub", sa.String(length=256), nullable=False),
        sa.Column("source_filename", sa.String(length=256), nullable=False),
        sa.Column("source_format", sa.String(length=32), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_preflight_record_tenant_created", "preflight_record", ["tenant_id", "created_at"])
    op.create_index("ix_preflight_record_tenant_sha", "preflight_record", ["tenant_id", "source_sha256"])


def downgrade() -> None:
    op.drop_index("ix_preflight_record_tenant_sha", table_name="preflight_record")
    op.drop_index("ix_preflight_record_tenant_created", table_name="preflight_record")
    op.drop_table("preflight_record")
    op.drop_index("ix_web_preference_tenant_user", table_name="web_preference")
    op.drop_table("web_preference")
