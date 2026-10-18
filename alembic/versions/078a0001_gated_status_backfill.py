# SPDX-License-Identifier: MPL-2.0
"""PLAN-078a：执行已结束、停在质量闸门的任务由 translating 回填为 gated。

Before this revision a run whose executor had finished stayed "translating" while it
waited at QA or review. The status column is a plain string, so no schema change is
needed; only existing rows are re-labelled so list, archive and delete treat them as
ended runs.

Runs already marked ``interrupted`` by the heartbeat while sitting at the gate are
deliberately left alone (the operator decides via scripts/plan078-qa-diagnose.py).

Revision ID: 078a0001
Revises: 074a0001
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "078a0001"
down_revision: Union[str, None] = "074a0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE translation_run_record
            SET status = 'gated'
            WHERE status = 'translating'
              AND quality_state IN ('qa_blocked', 'review_ready', 'qa_degraded')
            """
        )
    )


def downgrade() -> None:
    """Restore values the previous release understands; no information is lost.

    gated -> translating (what the old code wrote), and the two quality states the old
    code does not know map to their closest legacy meaning.
    """
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE qa_item SET severity = 'blocker' WHERE severity = 'unavailable'
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE translation_run_record
            SET quality_state = 'qa_blocked'
            WHERE quality_state = 'qa_unavailable'
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE translation_run_record
            SET quality_state = 'draft', status = 'translating'
            WHERE quality_state = 'changes_requested'
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE translation_run_record SET status = 'translating' WHERE status = 'gated'
            """
        )
    )
