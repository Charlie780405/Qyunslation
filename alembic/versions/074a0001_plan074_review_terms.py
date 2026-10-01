# SPDX-License-Identifier: MPL-2.0
"""PLAN-074：翻译任务审校定位与术语抽取元数据。"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "074a0001"
down_revision: Union[str, None] = "073a0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "review_segment", sa.Column("translation_run_id", sa.String(length=36), nullable=True)
    )
    op.add_column("review_segment", sa.Column("generation", sa.Integer(), nullable=True))
    op.add_column("review_segment", sa.Column("page_no", sa.Integer(), nullable=True))
    op.add_column("review_segment", sa.Column("bbox", sa.JSON(), nullable=True))
    op.create_index(
        "ix_review_segment_translation_run",
        "review_segment",
        ["translation_run_id", "generation", "role", "status"],
    )
    op.create_foreign_key(
        "fk_review_segment_translation_run",
        "review_segment",
        "translation_run_record",
        ["translation_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.add_column(
        "document_term_candidate",
        sa.Column("extraction_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("document_term_candidate", "extraction_metadata")
    op.drop_constraint("fk_review_segment_translation_run", "review_segment", type_="foreignkey")
    op.drop_index("ix_review_segment_translation_run", table_name="review_segment")
    op.drop_column("review_segment", "bbox")
    op.drop_column("review_segment", "page_no")
    op.drop_column("review_segment", "generation")
    op.drop_column("review_segment", "translation_run_id")
