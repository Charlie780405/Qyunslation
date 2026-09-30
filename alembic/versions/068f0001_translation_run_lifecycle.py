# SPDX-License-Identifier: MPL-2.0
"""PLAN-068: task lifecycle metadata for archive, restore and rename.

Revision ID: 068f0001
Revises: 066e0002
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "068f0001"
down_revision: Union[str, None] = "066e0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "translation_run_record",
        sa.Column("display_name", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "translation_run_record",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "translation_run_record",
        sa.Column("archived_by", sa.String(length=256), nullable=True),
    )
    op.create_index(
        "ix_translation_run_tenant_archived",
        "translation_run_record",
        ["tenant_id", "archived_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_translation_run_tenant_archived", table_name="translation_run_record")
    op.drop_column("translation_run_record", "archived_by")
    op.drop_column("translation_run_record", "archived_at")
    op.drop_column("translation_run_record", "display_name")
