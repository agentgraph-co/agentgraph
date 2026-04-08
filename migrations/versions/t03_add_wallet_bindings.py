"""Add wallet_bindings table for cross-provider wallet lookup.

Revision ID: t03
Revises: t02_avatar_url
Create Date: 2026-04-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "t03"
down_revision = "t02_avatar_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wallet_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("wallet_address", sa.String(255), nullable=False),
        sa.Column("chain", sa.String(50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["entity_id"], ["entities.id"], ondelete="CASCADE",
        ),
        sa.UniqueConstraint("wallet_address", "chain", name="uq_wallet_binding"),
    )
    op.create_index("ix_wallet_binding_address", "wallet_bindings", ["wallet_address"])
    op.create_index("ix_wallet_binding_entity", "wallet_bindings", ["entity_id"])


def downgrade() -> None:
    op.drop_index("ix_wallet_binding_entity", table_name="wallet_bindings")
    op.drop_index("ix_wallet_binding_address", table_name="wallet_bindings")
    op.drop_table("wallet_bindings")
