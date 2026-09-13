# SPDX-License-Identifier: MPL-2.0
"""PLAN-034f：Job.provenance JSON 列。

Revision ID: 034f0001
Revises: 034e0001
Create Date: 2026-09-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "034f0001"
down_revision: Union[str, None] = "034e0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("job", sa.Column("provenance", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("job", "provenance")
