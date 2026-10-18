# SPDX-License-Identifier: MPL-2.0
"""PLAN-078b：QA 处理闭环的数据模型（指纹/位置/类别、轮次差异、处置记录）。

Additive only: new nullable columns, one flag defaulting to "current", one new table.
Existing ``qa_item`` rows are left untouched; their fingerprint and class are computed on
read and stored the first time they are needed (a disposition is made).

Revision ID: 078b0001
Revises: 078a0002
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "078b0001"
down_revision: Union[str, None] = "078a0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("qa_item", sa.Column("round_id", sa.String(length=36), nullable=True))
    op.add_column("qa_item", sa.Column("fingerprint", sa.String(length=64), nullable=True))
    op.add_column("qa_item", sa.Column("location_json", sa.JSON(), nullable=True))
    op.add_column("qa_item", sa.Column("rule_class", sa.String(length=8), nullable=True))
    op.add_column(
        "qa_item",
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("qa_check_round", sa.Column("rule_set_version", sa.String(length=32), nullable=True))
    op.add_column("qa_check_round", sa.Column("artifact_digest", sa.String(length=64), nullable=True))
    op.add_column("qa_check_round", sa.Column("diff_json", sa.JSON(), nullable=True))
    op.create_table(
        "qa_disposition",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("translation_run_record.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("rule_class", sa.String(length=8), nullable=False),
        sa.Column("round_id", sa.String(length=36), nullable=True),
        sa.Column("artifact_digest", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=1024), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("actor_sub", sa.String(length=256), nullable=False),
        sa.Column("actor_role", sa.String(length=32), nullable=False),
        sa.Column("self_review", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_qa_disposition_run_fp", "qa_disposition", ["run_id", "generation", "fingerprint"]
    )


def downgrade() -> None:
    # Dispositions are audit records: dropping the table is the one irreversible step, so a
    # downgrade is only meant for a release rollback before any disposition was recorded.
    op.drop_index("ix_qa_disposition_run_fp", table_name="qa_disposition")
    op.drop_table("qa_disposition")
    op.drop_column("qa_check_round", "diff_json")
    op.drop_column("qa_check_round", "artifact_digest")
    op.drop_column("qa_check_round", "rule_set_version")
    op.drop_column("qa_item", "is_current")
    op.drop_column("qa_item", "rule_class")
    op.drop_column("qa_item", "location_json")
    op.drop_column("qa_item", "fingerprint")
    op.drop_column("qa_item", "round_id")
