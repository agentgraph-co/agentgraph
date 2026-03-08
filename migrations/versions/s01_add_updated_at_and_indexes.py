"""Add updated_at columns and performance indexes to mutable models

Adds updated_at (with onupdate=func.now()) to:
- trust_scores
- api_keys
- webhook_subscriptions
- transactions

Adds performance indexes:
- trust_scores.score
- api_keys.is_active
- webhook_subscriptions.is_active
- transactions.created_at

Revision ID: s01_updated_at_indexes
Revises: r07_trust_history
Create Date: 2026-03-08 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "s01_updated_at_indexes"
down_revision = "r07_trust_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Add updated_at to mutable models that lack it ---

    # trust_scores
    op.add_column(
        "trust_scores",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # api_keys
    op.add_column(
        "api_keys",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # webhook_subscriptions
    op.add_column(
        "webhook_subscriptions",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # transactions
    op.add_column(
        "transactions",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # --- Performance indexes ---

    op.create_index(
        "ix_trust_scores_score", "trust_scores", ["score"],
    )
    op.create_index(
        "ix_api_keys_active", "api_keys", ["is_active"],
    )
    op.create_index(
        "ix_webhooks_active", "webhook_subscriptions", ["is_active"],
    )
    op.create_index(
        "ix_transactions_created_at", "transactions", ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_created_at")
    op.drop_index("ix_webhooks_active")
    op.drop_index("ix_api_keys_active")
    op.drop_index("ix_trust_scores_score")

    op.drop_column("transactions", "updated_at")
    op.drop_column("webhook_subscriptions", "updated_at")
    op.drop_column("api_keys", "updated_at")
    op.drop_column("trust_scores", "updated_at")
