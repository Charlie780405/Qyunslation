# SPDX-License-Identifier: MPL-2.0
"""PLAN-073：concept 模板适用范围与 document_term_candidate.translation_run_id。"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "073a0001"
down_revision: Union[str, None] = "072a0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("concept", sa.Column("applies_to_profiles", sa.JSON(), nullable=True))
    op.add_column(
        "document_term_candidate",
        sa.Column("translation_run_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_document_term_candidate_translation_run",
        "document_term_candidate",
        ["translation_run_id", "status"],
    )
    op.create_foreign_key(
        "fk_document_term_candidate_translation_run",
        "document_term_candidate",
        "translation_run_record",
        ["translation_run_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_document_term_candidate_translation_run",
        "document_term_candidate",
        type_="foreignkey",
    )
    op.drop_index("ix_document_term_candidate_translation_run", table_name="document_term_candidate")
    op.drop_column("document_term_candidate", "translation_run_id")
    op.drop_column("concept", "applies_to_profiles")
