"""add_framework_security_scans

Revision ID: i04_framework_scans
Revises: i02_stripe
Create Date: 2026-02-21 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "i04_framework_scans"
down_revision = "i02_stripe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add framework columns to entities
    op.add_column(
        "entities",
        sa.Column("framework_source", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "entities",
        sa.Column("framework_trust_modifier", sa.Float(), nullable=True, server_default="1.0"),
    )

    # Create framework_security_scans table
    op.create_table(
        "framework_security_scans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("framework", sa.String(length=50), nullable=False),
        sa.Column("scan_result", sa.String(length=20), nullable=False),
        sa.Column("vulnerabilities", JSONB, server_default="[]"),
        sa.Column(
            "scanned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_framework_scans_entity",
        "framework_security_scans",
        ["entity_id"],
    )
    op.create_index(
        "ix_framework_scans_framework",
        "framework_security_scans",
        ["framework"],
    )
    op.create_index(
        "ix_framework_scans_scanned_at",
        "framework_security_scans",
        ["scanned_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_framework_scans_scanned_at", table_name="framework_security_scans")
    op.drop_index("ix_framework_scans_framework", table_name="framework_security_scans")
    op.drop_index("ix_framework_scans_entity", table_name="framework_security_scans")
    op.drop_table("framework_security_scans")
    op.drop_column("entities", "framework_trust_modifier")
    op.drop_column("entities", "framework_source")
