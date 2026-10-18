# SPDX-License-Identifier: MPL-2.0
"""PLAN-078a：QA 检查轮次表（每个任务代同时只有一个活跃轮次）。

Revision ID: 078a0002
Revises: 078a0001
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "078a0002"
down_revision: Union[str, None] = "078a0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVE = "status IN ('pending', 'running')"


def upgrade() -> None:
    op.create_table(
        "qa_check_round",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("translation_run_record.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("round_no", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False, server_default="auto"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "generation", "round_no", name="uq_qa_round_no"),
    )
    op.create_index(
        "uq_qa_round_active",
        "qa_check_round",
        ["run_id", "generation"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE),
        sqlite_where=sa.text(_ACTIVE),
    )


def downgrade() -> None:
    op.drop_index("uq_qa_round_active", table_name="qa_check_round")
    op.drop_table("qa_check_round")
