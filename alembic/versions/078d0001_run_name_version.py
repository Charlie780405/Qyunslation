# SPDX-License-Identifier: MPL-2.0
"""PLAN-078d：任务名称版本号（改名并发保护）。

Additive: one integer column defaulting to 0; existing rows need no backfill.

Revision ID: 078d0001
Revises: 078b0001
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "078d0001"
down_revision: Union[str, None] = "078b0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "translation_run_record",
        sa.Column("name_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("translation_run_record", "name_version")
