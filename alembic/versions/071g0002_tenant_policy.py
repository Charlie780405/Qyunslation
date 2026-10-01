# SPDX-License-Identifier: MPL-2.0
"""PLAN-071g：租户系统策略表（锁定字段与来源）。

Revision ID: 071g0002
Revises: 071i0001
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "071g0002"
down_revision: Union[str, None] = "071i0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_policy",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.String(length=256), nullable=True),
        sa.Column("updated_by", sa.String(length=256), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "key", name="uq_tenant_policy_key"),
    )


def downgrade() -> None:
    op.drop_table("tenant_policy")
