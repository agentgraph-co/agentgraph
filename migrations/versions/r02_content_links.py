"""Add content_links table for cross-referencing content

Revision ID: r02_content_links
Revises: r01_indexes_updated_at
Create Date: 2026-03-04 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "r02_content_links"
down_revision = "r01_indexes_updated_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_links",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("target_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("link_type", sa.String(30), nullable=False),
        sa.Column(
            "created_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_type IN ('post', 'entity', 'evolution_record', 'listing')",
            name="ck_content_link_source_type",
        ),
        sa.CheckConstraint(
            "target_type IN ('post', 'entity', 'evolution_record', 'listing')",
            name="ck_content_link_target_type",
        ),
        sa.CheckConstraint(
            "link_type IN ('mentions', 'references', 'related', 'replies_about')",
            name="ck_content_link_link_type",
        ),
        sa.UniqueConstraint(
            "source_type", "source_id", "target_type", "target_id", "link_type",
            name="uq_content_link",
        ),
    )

    op.create_index("ix_content_links_source", "content_links", ["source_type", "source_id"])
    op.create_index("ix_content_links_target", "content_links", ["target_type", "target_id"])
    op.create_index("ix_content_links_created_by", "content_links", ["created_by"])
    op.create_index("ix_content_links_link_type", "content_links", ["link_type"])
    op.create_index("ix_content_links_created_at", "content_links", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_content_links_created_at")
    op.drop_index("ix_content_links_link_type")
    op.drop_index("ix_content_links_created_by")
    op.drop_index("ix_content_links_target")
    op.drop_index("ix_content_links_source")
    op.drop_table("content_links")
