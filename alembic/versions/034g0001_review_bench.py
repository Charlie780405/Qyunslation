# SPDX-License-Identifier: MPL-2.0
"""PLAN-034g：review_segment / note / revision。

Revision ID: 034g0001
Revises: 034f0001
Create Date: 2026-09-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "034g0001"
down_revision: Union[str, None] = "034f0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "review_segment",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("block_id", sa.String(length=128), nullable=True),
        sa.Column("policy", sa.String(length=32), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("machine_text", sa.Text(), nullable=False),
        sa.Column("revised_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("decided_by", sa.String(length=256), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["job.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_review_segment_job_status", "review_segment", ["job_id", "status"]
    )
    op.create_index("ix_review_segment_source_sha", "review_segment", ["source_sha256"])

    op.create_table(
        "review_note",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("segment_id", sa.String(length=36), nullable=False),
        sa.Column("author_sub", sa.String(length=256), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["segment_id"], ["review_segment.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_note_segment", "review_note", ["segment_id"])

    op.create_table(
        "review_revision",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("segment_id", sa.String(length=36), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("target_text", sa.Text(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("actor_sub", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["segment_id"], ["review_segment.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("segment_id", "version", name="uq_review_revision_seg_ver"),
    )
    op.create_index(
        "ix_review_revision_source_sha", "review_revision", ["source_sha256"]
    )


def downgrade() -> None:
    op.drop_index("ix_review_revision_source_sha", table_name="review_revision")
    op.drop_table("review_revision")
    op.drop_index("ix_review_note_segment", table_name="review_note")
    op.drop_table("review_note")
    op.drop_index("ix_review_segment_source_sha", table_name="review_segment")
    op.drop_index("ix_review_segment_job_status", table_name="review_segment")
    op.drop_table("review_segment")
