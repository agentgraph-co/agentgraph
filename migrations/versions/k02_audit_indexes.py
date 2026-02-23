"""Add indexes identified by performance audit (Task 75 batch 2).

Covers: notifications ordering, DM unread counts, listing filters,
webhook dispatch lookups.

Revision ID: k02_audit_indexes
Revises: k01_performance_indexes
Create Date: 2026-02-23 01:00:00.000000
"""
from __future__ import annotations

from alembic import op

revision = "k02_audit_indexes"
down_revision = "k01_performance_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Notifications: composite covering WHERE entity_id + ORDER BY created_at
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notifications_entity_created "
        "ON notifications (entity_id, created_at DESC)"
    )

    # Notifications: kind filter for preference-based filtering
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notifications_entity_kind "
        "ON notifications (entity_id, kind)"
    )

    # Direct messages: unread count per conversation
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dm_conv_read "
        "ON direct_messages (conversation_id, is_read)"
    )

    # Listings: pricing model filter
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_listings_pricing_model "
        "ON listings (pricing_model)"
    )

    # Listings: featured + created_at for browse ordering
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_listings_featured_created "
        "ON listings (is_featured DESC, created_at DESC)"
    )

    # Webhook subscriptions: active dispatch lookup (GIN on array column)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_webhooks_active_types "
        "ON webhook_subscriptions USING gin (event_types) WHERE is_active = true"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_webhooks_active_types")
    op.execute("DROP INDEX IF EXISTS ix_listings_featured_created")
    op.execute("DROP INDEX IF EXISTS ix_listings_pricing_model")
    op.execute("DROP INDEX IF EXISTS ix_dm_conv_read")
    op.execute("DROP INDEX IF EXISTS ix_notifications_entity_kind")
    op.execute("DROP INDEX IF EXISTS ix_notifications_entity_created")
