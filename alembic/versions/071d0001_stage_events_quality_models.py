# SPDX-License-Identifier: MPL-2.0
"""PLAN-071d/e/g：阶段事件、质量状态、审核与模型配置表。

Revision ID: 071d0001
Revises: 068f0001
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "071d0001"
down_revision: Union[str, None] = "068f0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "translation_run_record",
        sa.Column("quality_state", sa.String(length=32), nullable=False, server_default="draft"),
    )
    op.add_column(
        "translation_run_record",
        sa.Column("document_classification", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "translation_run_record",
        sa.Column("model_profile_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "preflight_record",
        sa.Column("document_classification", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "preflight_record",
        sa.Column("model_profile_id", sa.String(length=128), nullable=True),
    )

    op.create_table(
        "translation_stage_event",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("translation_run_record.id", ondelete="CASCADE"), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("units_done", sa.Integer(), nullable=True),
        sa.Column("units_total", sa.Integer(), nullable=True),
        sa.Column("message", sa.String(length=512), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.UniqueConstraint("run_id", "generation", "sequence", name="uq_stage_event_seq"),
    )
    op.create_index(
        "ix_stage_event_run_gen_seq",
        "translation_stage_event",
        ["run_id", "generation", "sequence"],
    )

    op.create_table(
        "qa_item",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("translation_run_record.id", ondelete="CASCADE"), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("message", sa.String(length=1024), nullable=False),
        sa.Column("object_id", sa.String(length=128), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("reviewer_note", sa.String(length=1024), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_qa_item_run_gen", "qa_item", ["run_id", "generation"])

    op.create_table(
        "review_decision",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("translation_run_record.id", ondelete="CASCADE"), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=256), nullable=False),
        sa.Column("comment", sa.String(length=2048), nullable=True),
        sa.Column("qa_snapshot", sa.JSON(), nullable=False),
        sa.Column("term_snapshot", sa.JSON(), nullable=False),
        sa.Column("model_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_review_decision_run_gen", "review_decision", ["run_id", "generation"])

    op.create_table(
        "model_profile_version",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("profile_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=256), nullable=False),
        sa.Column("reported_version", sa.String(length=256), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("experimental", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("probe_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_model_profile_id_created", "model_profile_version", ["profile_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_model_profile_id_created", table_name="model_profile_version")
    op.drop_table("model_profile_version")
    op.drop_index("ix_review_decision_run_gen", table_name="review_decision")
    op.drop_table("review_decision")
    op.drop_index("ix_qa_item_run_gen", table_name="qa_item")
    op.drop_table("qa_item")
    op.drop_index("ix_stage_event_run_gen_seq", table_name="translation_stage_event")
    op.drop_table("translation_stage_event")
    op.drop_column("preflight_record", "model_profile_id")
    op.drop_column("preflight_record", "document_classification")
    op.drop_column("translation_run_record", "model_profile_id")
    op.drop_column("translation_run_record", "document_classification")
    op.drop_column("translation_run_record", "quality_state")
