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

revision = "s03_missing_columns"
down_revision = "s02_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # --- entities.operator_approved (task #184) ---
    conn.execute(sa.text(
        "ALTER TABLE entities ADD COLUMN IF NOT EXISTS "
        "operator_approved BOOLEAN NOT NULL DEFAULT false"
    ))

    # --- entities.onboarding_data (bot onboarding) ---
    conn.execute(sa.text(
        "ALTER TABLE entities ADD COLUMN IF NOT EXISTS "
        "onboarding_data JSONB DEFAULT '{}'::jsonb"
    ))

    # --- webhook_delivery_logs table (task #191) ---
    conn.execute(sa.text(
        "CREATE TABLE IF NOT EXISTS webhook_delivery_logs ("
        "  id UUID PRIMARY KEY,"
        "  subscription_id UUID NOT NULL"
        "    REFERENCES webhook_subscriptions(id) ON DELETE CASCADE,"
        "  event_type VARCHAR(100) NOT NULL,"
        "  payload JSONB NOT NULL DEFAULT '{}'::jsonb,"
        "  status_code INTEGER,"
        "  success BOOLEAN NOT NULL DEFAULT false,"
        "  error_message TEXT,"
        "  attempt_number INTEGER NOT NULL DEFAULT 1,"
        "  duration_ms INTEGER,"
        "  created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_delivery_logs_subscription "
        "ON webhook_delivery_logs (subscription_id)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_delivery_logs_created_at "
        "ON webhook_delivery_logs (created_at)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_delivery_logs_event_type "
        "ON webhook_delivery_logs (event_type)"
    ))


def downgrade() -> None:
    op.drop_index("ix_delivery_logs_event_type", table_name="webhook_delivery_logs")
    op.drop_index("ix_delivery_logs_created_at", table_name="webhook_delivery_logs")
    op.drop_index("ix_delivery_logs_subscription", table_name="webhook_delivery_logs")
    op.drop_table("webhook_delivery_logs")
    op.drop_column("entities", "onboarding_data")
    op.drop_column("entities", "operator_approved")
