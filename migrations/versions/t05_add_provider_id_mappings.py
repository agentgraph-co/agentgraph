"""Add provider_id_mappings table for external provider bilateral integration.

Maps AgentGraph entity IDs to provider-specific IDs (RNWY agent ID,
MoltBridge DID, AgentID agent_id) so the gateway can query external
providers with the correct identifier.

Revision ID: t05
Revises: t04
Create Date: 2026-04-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "t05"
down_revision = "t04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_id_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_entity_id", sa.String(255), nullable=False),
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
        sa.UniqueConstraint(
            "entity_id", "provider", name="uq_provider_id_mapping",
        ),
    )
    op.create_index(
        "ix_provider_id_entity", "provider_id_mappings", ["entity_id"],
    )
    op.create_index(
        "ix_provider_id_provider", "provider_id_mappings",
        ["provider", "provider_entity_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_provider_id_provider", table_name="provider_id_mappings")
    op.drop_index("ix_provider_id_entity", table_name="provider_id_mappings")
    op.drop_table("provider_id_mappings")
