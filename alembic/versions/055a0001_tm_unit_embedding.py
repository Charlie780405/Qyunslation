# SPDX-License-Identifier: MPL-2.0
"""PLAN-055：tm_unit_embedding 旁路表。

Revision ID: 055a0001
Revises: 034g0001
Create Date: 2026-09-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "055a0001"
down_revision: Union[str, None] = "034g0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tm_unit_embedding",
        sa.Column("unit_id", sa.String(length=36), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("vector", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["unit_id"], ["tm_unit.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("unit_id"),
    )


def downgrade() -> None:
    op.drop_table("tm_unit_embedding")
