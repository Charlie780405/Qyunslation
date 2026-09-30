# SPDX-License-Identifier: MPL-2.0
"""PLAN-066e: durable TranslationRun ledger for the Vue workbench.

Revision ID: 066e0001
Revises: 066c0001
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "066e0001"
down_revision: Union[str, None] = "066c0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "translation_run_record",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("preflight_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("actor_sub", sa.String(length=256), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=64), nullable=False),
        sa.Column("profile", sa.String(length=128), nullable=False),
        sa.Column("settings_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=True),
        sa.Column("external_task_id", sa.String(length=256), nullable=True),
        sa.Column("manifest_version", sa.String(length=128), nullable=True),
        sa.Column("qa_summary", sa.JSON(), nullable=False),
        sa.Column("term_summary", sa.JSON(), nullable=False),
        sa.Column("degradation_reason", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["preflight_id"], ["preflight_record.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("preflight_id", "generation", name="uq_translation_run_generation"),
        sa.UniqueConstraint("tenant_id", "idempotency_key_hash", name="uq_translation_run_idempotency"),
    )
    op.create_index("ix_translation_run_tenant_created", "translation_run_record", ["tenant_id", "created_at"])
    op.create_index("ix_translation_run_tenant_status", "translation_run_record", ["tenant_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_translation_run_tenant_status", table_name="translation_run_record")
    op.drop_index("ix_translation_run_tenant_created", table_name="translation_run_record")
    op.drop_table("translation_run_record")
