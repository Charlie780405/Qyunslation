# SPDX-License-Identifier: MPL-2.0
"""PLAN-058：修复首次部署时缺少 Python pgvector 导致的 JSON 向量列。

Revision ID: 058b0001
Revises: 058a0001
Create Date: 2026-09-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "058b0001"
down_revision: Union[str, None] = "058a0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # 058a0001 can only create a JSON fallback when the Python pgvector
    # package was absent at migration time.  The database extension is the
    # authoritative prerequisite for the production vector type and HNSW.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    column_type = bind.execute(
        sa.text(
            """
            SELECT udt_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'concept_term_embedding'
              AND column_name = 'vector'
            """
        )
    ).scalar()
    if column_type != "vector":
        op.execute(
            """
            ALTER TABLE concept_term_embedding
            ALTER COLUMN vector TYPE vector(1024)
            USING vector::text::vector(1024)
            """
        )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_concept_term_embedding_vector_hnsw
        ON concept_term_embedding USING hnsw (vector vector_cosine_ops)
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DROP INDEX IF EXISTS ix_concept_term_embedding_vector_hnsw")
    column_type = bind.execute(
        sa.text(
            """
            SELECT udt_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'concept_term_embedding'
              AND column_name = 'vector'
            """
        )
    ).scalar()
    if column_type == "vector":
        op.execute(
            """
            ALTER TABLE concept_term_embedding
            ALTER COLUMN vector TYPE json
            USING to_jsonb(vector)::json
            """
        )
