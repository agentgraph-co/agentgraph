"""Add org_usage_records table and organization_id to api_keys

Revision ID: j04_org_usage_metering
Revises: j02_capability_marketplace
Create Date: 2026-02-22 12:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "j04_org_usage_metering"
down_revision = "j02_capability_marketplace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- org_usage_records table ---
    op.create_table(
        "org_usage_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("api_calls", sa.Integer(), server_default="0"),
        sa.Column("storage_bytes", sa.Integer(), server_default="0"),
        sa.Column("active_agents", sa.Integer(), server_default="0"),
        sa.Column("active_members", sa.Integer(), server_default="0"),
        sa.Column("extra_metadata", JSONB, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "organization_id", "period_start", name="uq_org_usage_period",
        ),
    )
    op.create_index("ix_usage_org", "org_usage_records", ["organization_id"])
    op.create_index(
        "ix_usage_period", "org_usage_records", ["period_start", "period_end"],
    )

    # --- Add organization_id to api_keys ---
    op.add_column(
        "api_keys",
        sa.Column(
            "organization_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "organization_id")
    op.drop_table("org_usage_records")
