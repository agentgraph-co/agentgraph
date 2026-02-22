"""Add disputes table and ESCROW/DISPUTED transaction statuses

Revision ID: j01_disputes_escrow
Revises: i09_sso_config
Create Date: 2026-02-22 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "j01_disputes_escrow"
down_revision = "i09_sso_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new enum values to transactionstatus (uppercase to match existing convention)
    op.execute("ALTER TYPE transactionstatus ADD VALUE IF NOT EXISTS 'ESCROW'")
    op.execute("ALTER TYPE transactionstatus ADD VALUE IF NOT EXISTS 'DISPUTED'")

    # Create disputes table
    op.create_table(
        "disputes",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "transaction_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transactions.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column(
            "opened_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            server_default="open",
            nullable=False,
        ),
        sa.Column("resolution", sa.String(20), nullable=True),
        sa.Column("resolution_amount_cents", sa.Integer(), nullable=True),
        sa.Column(
            "resolved_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id"),
            nullable=True,
        ),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column(
            "deadline",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_index("ix_disputes_status", "disputes", ["status"])
    op.create_index("ix_disputes_transaction", "disputes", ["transaction_id"])
    op.create_index("ix_disputes_opened_by", "disputes", ["opened_by"])


def downgrade() -> None:
    op.drop_index("ix_disputes_opened_by", table_name="disputes")
    op.drop_index("ix_disputes_transaction", table_name="disputes")
    op.drop_index("ix_disputes_status", table_name="disputes")
    op.drop_table("disputes")
    # Note: Postgres does not support removing enum values easily.
    # The ESCROW/DISPUTED values will remain in the enum type.
