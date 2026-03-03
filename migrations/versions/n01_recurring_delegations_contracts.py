"""Add recurring delegation columns and service_contracts table.

Revision ID: n01_recurring_delegations_contracts
Revises: m02_add_population_alerts
Create Date: 2026-03-03 16:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "n01_recurring_delegations_contracts"
down_revision = "m02_add_population_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Add recurring delegation columns to delegations table ---
    op.add_column(
        "delegations",
        sa.Column("recurrence", sa.String(20), nullable=True),
    )
    op.add_column(
        "delegations",
        sa.Column(
            "recurrence_count", sa.Integer(), server_default="0", nullable=False,
        ),
    )
    op.add_column(
        "delegations",
        sa.Column("max_recurrences", sa.Integer(), nullable=True),
    )
    op.add_column(
        "delegations",
        sa.Column(
            "parent_delegation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("delegations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_delegations_parent", "delegations", ["parent_delegation_id"],
    )
    op.create_index(
        "ix_delegations_recurrence", "delegations", ["recurrence"],
    )

    # --- Create service_contracts table ---
    op.create_table(
        "service_contracts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "provider_entity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "consumer_entity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "listing_id",
            UUID(as_uuid=True),
            sa.ForeignKey("listings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("terms", JSONB, nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            server_default="active",
            nullable=False,
        ),
        sa.Column("paused_by", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_service_contracts_provider", "service_contracts", ["provider_entity_id"],
    )
    op.create_index(
        "ix_service_contracts_consumer", "service_contracts", ["consumer_entity_id"],
    )
    op.create_index(
        "ix_service_contracts_status", "service_contracts", ["status"],
    )
    op.create_index(
        "ix_service_contracts_listing", "service_contracts", ["listing_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_service_contracts_listing", table_name="service_contracts")
    op.drop_index("ix_service_contracts_status", table_name="service_contracts")
    op.drop_index("ix_service_contracts_consumer", table_name="service_contracts")
    op.drop_index("ix_service_contracts_provider", table_name="service_contracts")
    op.drop_table("service_contracts")

    op.drop_index("ix_delegations_recurrence", table_name="delegations")
    op.drop_index("ix_delegations_parent", table_name="delegations")
    op.drop_column("delegations", "parent_delegation_id")
    op.drop_column("delegations", "max_recurrences")
    op.drop_column("delegations", "recurrence_count")
    op.drop_column("delegations", "recurrence")
