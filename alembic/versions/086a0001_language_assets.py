# SPDX-License-Identifier: MPL-2.0
"""PLAN-086a: versioned terminology/style/pitfall assets and controlled imports."""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "086a0001"
down_revision: Union[str, None] = "078e0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "language_asset_release",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=True),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False, server_default="tenant"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("src_lang", sa.String(length=16), nullable=False, server_default="en"),
        sa.Column("tgt_lang", sa.String(length=16), nullable=False, server_default="zh"),
        sa.Column("document_profile", sa.String(length=128), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("license", sa.String(length=256), nullable=True),
        sa.Column("provenance", sa.String(length=512), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("published_by", sa.String(length=256), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=256), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "project_id", "asset_type", "scope", "version", name="uq_language_asset_release_version"),
    )
    op.create_index("ix_language_asset_release_lookup", "language_asset_release", ["tenant_id", "project_id", "asset_type", "status"])
    op.create_table(
        "language_asset_release_item",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("release_id", sa.String(length=36), sa.ForeignKey("language_asset_release.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_key", sa.String(length=512), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("release_id", "item_key", name="uq_language_asset_release_item"),
    )
    op.create_index("ix_language_asset_release_item_release", "language_asset_release_item", ["release_id"])
    op.create_table(
        "language_asset_import_batch",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_sub", sa.String(length=256), nullable=False),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=256), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("license", sa.String(length=256), nullable=True),
        sa.Column("provenance", sa.String(length=512), nullable=True),
        sa.Column("scope", sa.String(length=32), nullable=False, server_default="tenant"),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="previewed"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("preview_json", sa.JSON(), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=True),
        sa.Column("release_id", sa.String(length=36), nullable=True),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "source_sha256", "asset_type", name="uq_language_asset_import_digest"),
    )
    op.create_index("ix_language_asset_import_tenant_created", "language_asset_import_batch", ["tenant_id", "created_at"])
    op.create_table(
        "style_profile",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("src_lang", sa.String(length=16), nullable=False, server_default="en"),
        sa.Column("tgt_lang", sa.String(length=16), nullable=False, server_default="zh"),
        sa.Column("document_profile", sa.String(length=128), nullable=True),
        sa.Column("scope", sa.String(length=32), nullable=False, server_default="tenant"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column("release_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=256), nullable=False),
        sa.Column("updated_by", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_style_profile_scope", "style_profile", ["tenant_id", "project_id", "status"])
    op.create_table(
        "quality_rule_definition",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("project.id", ondelete="CASCADE"), nullable=True),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("trigger", sa.Text(), nullable=False, server_default=""),
        sa.Column("detector", sa.String(length=32), nullable=False, server_default="deterministic"),
        sa.Column("severity", sa.String(length=32), nullable=False, server_default="warning"),
        sa.Column("remediation", sa.Text(), nullable=False, server_default=""),
        sa.Column("false_positive", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("scope", sa.String(length=32), nullable=False, server_default="tenant"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("release_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=256), nullable=False),
        sa.Column("updated_by", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "code", name="uq_quality_rule_tenant_code"),
    )
    op.create_index("ix_quality_rule_scope_status", "quality_rule_definition", ["tenant_id", "scope", "status"])


def downgrade() -> None:
    op.drop_index("ix_quality_rule_scope_status", table_name="quality_rule_definition")
    op.drop_table("quality_rule_definition")
    op.drop_index("ix_style_profile_scope", table_name="style_profile")
    op.drop_table("style_profile")
    op.drop_index("ix_language_asset_import_tenant_created", table_name="language_asset_import_batch")
    op.drop_table("language_asset_import_batch")
    op.drop_index("ix_language_asset_release_item_release", table_name="language_asset_release_item")
    op.drop_table("language_asset_release_item")
    op.drop_index("ix_language_asset_release_lookup", table_name="language_asset_release")
    op.drop_table("language_asset_release")
