# SPDX-License-Identifier: MPL-2.0
"""PLAN-060：持久化 Gradio 工作台术语运行。

Revision ID: 060a0001
Revises: 058b0001
Create Date: 2026-09-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "060a0001"
down_revision: Union[str, None] = "058b0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workbench_translation_run",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("job_id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("actor_sub", sa.String(256), nullable=False),
        sa.Column("engine", sa.String(64), nullable=False, server_default="gradio"),
        sa.Column("source_format", sa.String(32), nullable=False),
        sa.Column("external_task_id", sa.String(256), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="submitted"),
        sa.Column("termbase_version", sa.String(128), nullable=True),
        sa.Column("term_policy", sa.JSON(), nullable=True),
        sa.Column("degradation_reason", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["job.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_workbench_translation_run_job"),
    )
    op.create_index(
        "ix_workbench_translation_run_actor",
        "workbench_translation_run",
        ["tenant_id", "actor_sub", "created_at"],
    )
    op.create_index(
        "ix_workbench_translation_run_state",
        "workbench_translation_run",
        ["tenant_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_workbench_translation_run_state", table_name="workbench_translation_run")
    op.drop_index("ix_workbench_translation_run_actor", table_name="workbench_translation_run")
    op.drop_table("workbench_translation_run")
