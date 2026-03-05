"""Add provisional registration fields to entities

Revision ID: p01_provisional_reg
Revises: o02_agent_discovery_idx
Create Date: 2026-03-05 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p01_provisional_reg"
down_revision = "o02_agent_discovery_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "entities",
        sa.Column("is_provisional", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "entities",
        sa.Column("claim_token", sa.String(64), nullable=True),
    )
    op.add_column(
        "entities",
        sa.Column("provisional_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_entities_is_provisional",
        "entities",
        ["is_provisional"],
        unique=False,
    )
    op.create_index(
        "ix_entities_claim_token",
        "entities",
        ["claim_token"],
        unique=True,
        postgresql_where=sa.text("claim_token IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_entities_claim_token", table_name="entities")
    op.drop_index("ix_entities_is_provisional", table_name="entities")
    op.drop_column("entities", "provisional_expires_at")
    op.drop_column("entities", "claim_token")
    op.drop_column("entities", "is_provisional")
