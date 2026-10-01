# SPDX-License-Identifier: MPL-2.0
"""PLAN-071i：历史成功任务标记 legacy_unverified。

Revision ID: 071i0001
Revises: 071d0001
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "071i0001"
down_revision: Union[str, None] = "071d0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE translation_run_record
            SET quality_state = 'legacy_unverified'
            WHERE status = 'succeeded'
              AND (quality_state IS NULL OR quality_state IN ('draft', ''))
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE translation_artifact
            SET kind = 'legacy'
            WHERE formal_export IS TRUE
              AND kind = 'formal'
              AND run_id IN (
                SELECT id FROM translation_run_record WHERE quality_state = 'legacy_unverified'
              )
            """
        )
    )


def downgrade() -> None:
    # Data migration is intentionally not reversed (keep audit trail).
    pass
