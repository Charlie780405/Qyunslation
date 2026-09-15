# SPDX-License-Identifier: MPL-2.0
"""PLAN-063a：workbench_translation_run.excluded_stats。

Revision ID: 063a0001
Revises: 060a0001
Create Date: 2026-09-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "063a0001"
down_revision: Union[str, None] = "060a0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workbench_translation_run", sa.Column("excluded_stats", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("workbench_translation_run", "excluded_stats")
