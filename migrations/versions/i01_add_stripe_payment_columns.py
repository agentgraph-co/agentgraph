"""add_stripe_payment_columns

Revision ID: i01_stripe
Revises: h01_add_analytics_events_table
Create Date: 2026-02-21 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "i01_stripe"
down_revision = "h01_analytics_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Entity: add stripe_account_id
    op.add_column(
        "entities",
        sa.Column("stripe_account_id", sa.String(length=255), nullable=True),
    )

    # Transaction: add Stripe payment fields
    op.add_column(
        "transactions",
        sa.Column("stripe_payment_intent_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("stripe_transfer_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("platform_fee_cents", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_transactions_stripe_pi",
        "transactions",
        ["stripe_payment_intent_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_stripe_pi", table_name="transactions")
    op.drop_column("transactions", "platform_fee_cents")
    op.drop_column("transactions", "stripe_transfer_id")
    op.drop_column("transactions", "stripe_payment_intent_id")
    op.drop_column("entities", "stripe_account_id")
