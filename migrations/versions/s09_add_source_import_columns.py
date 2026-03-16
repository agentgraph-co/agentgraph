"""Add source import tracking columns to entities table.

Revision ID: s09_source_import
Revises: s08_linked_accounts
Create Date: 2026-03-16 12:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "s09_source_import"
down_revision = "s08_linked_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("entities", sa.Column("source_url", sa.String(1000), nullable=True))
    op.add_column("entities", sa.Column("source_type", sa.String(30), nullable=True))
    op.add_column(
        "entities",
        sa.Column("source_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_entities_source_url", "entities", ["source_url"])


def downgrade() -> None:
    op.drop_index("ix_entities_source_url", table_name="entities")
    op.drop_column("entities", "source_verified_at")
    op.drop_column("entities", "source_type")
    op.drop_column("entities", "source_url")
