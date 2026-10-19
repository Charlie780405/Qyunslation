# SPDX-License-Identifier: MPL-2.0
"""PLAN-078e：回收站字段、批量选择快照、批量操作幂等记录。

Additive only: nullable columns on ``translation_run_record`` (existing rows are "not in the
bin"), one index, and two new tables. Nothing is backfilled.

Revision ID: 078e0001
Revises: 078d0001
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "078e0001"
down_revision: Union[str, None] = "078d0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("translation_run_record", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("translation_run_record", sa.Column("deleted_by", sa.String(length=256), nullable=True))
    op.add_column("translation_run_record", sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True))
    op.add_column("translation_run_record", sa.Column("purge_status", sa.String(length=16), nullable=True))
    op.add_column("translation_run_record", sa.Column("purge_error", sa.Text(), nullable=True))
    op.create_index(
        "ix_translation_run_tenant_deleted", "translation_run_record", ["tenant_id", "deleted_at"]
    )
    op.create_table(
        "run_selection",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_sub", sa.String(length=256), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("run_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_run_selection_expires", "run_selection", ["expires_at"])
    op.create_table(
        "run_batch_operation",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_sub", sa.String(length=256), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "actor_sub", "key_hash", name="uq_run_batch_operation_key"),
    )


def downgrade() -> None:
    op.drop_table("run_batch_operation")
    op.drop_index("ix_run_selection_expires", table_name="run_selection")
    op.drop_table("run_selection")
    op.drop_index("ix_translation_run_tenant_deleted", table_name="translation_run_record")
    for column in ("purge_error", "purge_status", "purge_after", "deleted_by", "deleted_at"):
        op.drop_column("translation_run_record", column)
