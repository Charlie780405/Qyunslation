# SPDX-License-Identifier: MPL-2.0
"""PLAN-066c: server-side OIDC login state and opaque BFF sessions.

Revision ID: 066c0001
Revises: 066a0001
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "066c0001"
down_revision: Union[str, None] = "066a0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "oidc_login_state",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("code_verifier", sa.String(length=256), nullable=False),
        sa.Column("nonce", sa.String(length=256), nullable=False),
        sa.Column("return_to", sa.String(length=512), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash"),
    )
    op.create_index("ix_oidc_login_state_expires", "oidc_login_state", ["expires_at"])

    op.create_table(
        "web_session",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_hash", sa.String(length=64), nullable=False),
        sa.Column("tenant_slug", sa.String(length=128), nullable=False),
        sa.Column("user_sub", sa.String(length=256), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=True),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("token_blob", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_web_session_hash", "web_session", ["session_hash"], unique=True)
    op.create_index("ix_web_session_expires", "web_session", ["expires_at"])
    op.create_index("ix_web_session_user", "web_session", ["tenant_slug", "user_sub"])


def downgrade() -> None:
    op.drop_index("ix_web_session_user", table_name="web_session")
    op.drop_index("ix_web_session_expires", table_name="web_session")
    op.drop_index("ix_web_session_hash", table_name="web_session")
    op.drop_table("web_session")
    op.drop_index("ix_oidc_login_state_expires", table_name="oidc_login_state")
    op.drop_table("oidc_login_state")
