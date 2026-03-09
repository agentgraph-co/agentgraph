"""Add missing columns: entities.operator_approved, entities.onboarding_data,
and webhook_delivery_logs table

These columns/tables were added to models.py but never had Alembic migrations.
The test conftest.py uses IF NOT EXISTS DDL to create them, but production
relies on Alembic.

Revision ID: s03_missing_columns
Revises: s02_merge_heads
Create Date: 2026-03-09 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "s03_missing_columns"
down_revision = "s02_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- entities.operator_approved (task #184) ---
    op.add_column(
        "entities",
        sa.Column(
            "operator_approved",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )

    # --- entities.onboarding_data (bot onboarding) ---
    op.add_column(
        "entities",
        sa.Column(
            "onboarding_data",
            postgresql.JSONB(),
            server_default="{}",
            nullable=True,
        ),
    )

    # --- webhook_delivery_logs table (task #191) ---
    op.create_table(
        "webhook_delivery_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column(
            "success",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "attempt_number",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_delivery_logs_subscription",
        "webhook_delivery_logs",
        ["subscription_id"],
    )
    op.create_index(
        "ix_delivery_logs_created_at",
        "webhook_delivery_logs",
        ["created_at"],
    )
    op.create_index(
        "ix_delivery_logs_event_type",
        "webhook_delivery_logs",
        ["event_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_delivery_logs_event_type", table_name="webhook_delivery_logs")
    op.drop_index("ix_delivery_logs_created_at", table_name="webhook_delivery_logs")
    op.drop_index("ix_delivery_logs_subscription", table_name="webhook_delivery_logs")
    op.drop_table("webhook_delivery_logs")
    op.drop_column("entities", "onboarding_data")
    op.drop_column("entities", "operator_approved")
