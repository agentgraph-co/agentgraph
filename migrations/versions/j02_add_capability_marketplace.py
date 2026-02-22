"""Add capability marketplace columns to listings and evolution_records

Revision ID: j02_capability_marketplace
Revises: j03_aip_tables
Create Date: 2026-02-22 12:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "j02_capability_marketplace"
down_revision = "j03_aip_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add source_evolution_record_id to listings table
    op.add_column(
        "listings",
        sa.Column(
            "source_evolution_record_id",
            UUID(as_uuid=True),
            sa.ForeignKey("evolution_records.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_listings_source_evo",
        "listings",
        ["source_evolution_record_id"],
    )

    # Add source_listing_id to evolution_records table
    op.add_column(
        "evolution_records",
        sa.Column(
            "source_listing_id",
            UUID(as_uuid=True),
            sa.ForeignKey("listings.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_evolution_source_listing",
        "evolution_records",
        ["source_listing_id"],
    )

    # Add license_type to evolution_records table
    op.add_column(
        "evolution_records",
        sa.Column(
            "license_type",
            sa.String(30),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_evolution_source_listing", table_name="evolution_records")
    op.drop_column("evolution_records", "license_type")
    op.drop_column("evolution_records", "source_listing_id")
    op.drop_index("ix_listings_source_evo", table_name="listings")
    op.drop_column("listings", "source_evolution_record_id")
