"""Add did_status state machine columns to did_documents

Revision ID: s01_did_status
Revises: r07_trust_history
Create Date: 2026-03-08 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "s01_did_status"
down_revision = "r07_trust_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the enum type first
    did_status_enum = sa.Enum("PROVISIONAL", "FULL", "REVOKED", name="didstatus")
    did_status_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "did_documents",
        sa.Column(
            "did_status",
            did_status_enum,
            server_default="FULL",
            nullable=False,
        ),
    )
    op.add_column(
        "did_documents",
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "did_documents",
        sa.Column("promoted_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "did_documents",
        sa.Column("promotion_reason", sa.String(200), nullable=True),
    )
    op.create_index(
        "ix_did_documents_did_status",
        "did_documents",
        ["did_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_did_documents_did_status", table_name="did_documents")
    op.drop_column("did_documents", "promotion_reason")
    op.drop_column("did_documents", "promoted_by")
    op.drop_column("did_documents", "promoted_at")
    op.drop_column("did_documents", "did_status")
    sa.Enum(name="didstatus").drop(op.get_bind(), checkfirst=True)
