# SPDX-License-Identifier: MPL-2.0
"""PLAN-072：上传会话、审核草稿、任务心跳。

Revision ID: 072a0001
Revises: 071g0002
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "072a0001"
down_revision: Union[str, None] = "071g0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "translation_run_record",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "translation_run_record",
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
    )
    op.create_table(
        "upload_session",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_sub", sa.String(length=256), nullable=False),
        sa.Column("source_filename", sa.String(length=256), nullable=False),
        sa.Column("source_format", sa.String(length=32), nullable=False),
        sa.Column("total_size", sa.Integer(), nullable=False),
        sa.Column("received_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expected_sha256", sa.String(length=64), nullable=True),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="uploading"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_upload_session_tenant_actor",
        "upload_session",
        ["tenant_id", "actor_sub", "created_at"],
    )
    op.create_table(
        "review_draft",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("translation_run_record.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=256), nullable=False),
        sa.Column("comment", sa.String(length=2048), nullable=True),
        sa.Column("resolved_qa_ids", sa.JSON(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "run_id", "generation", "user_id", name="uq_review_draft_run_gen_user"
        ),
    )


def downgrade() -> None:
    op.drop_table("review_draft")
    op.drop_index("ix_upload_session_tenant_actor", table_name="upload_session")
    op.drop_table("upload_session")
    op.drop_column("translation_run_record", "lease_owner")
    op.drop_column("translation_run_record", "heartbeat_at")
