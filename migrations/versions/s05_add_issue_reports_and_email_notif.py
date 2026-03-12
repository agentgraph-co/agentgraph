"""Add issue_reports table and email_notifications_enabled to notification_preferences.

Revision ID: s05_issue_reports_email_notif
Revises: s04_registration_ip
Create Date: 2026-03-12 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "s05_issue_reports_email_notif"
down_revision = "s04_registration_ip"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Add email_notifications_enabled to notification_preferences
    conn.execute(sa.text(
        "ALTER TABLE notification_preferences "
        "ADD COLUMN IF NOT EXISTS email_notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE"
    ))

    # Create issue_reports table
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS issue_reports (
            id UUID PRIMARY KEY,
            post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
            bot_reply_id UUID REFERENCES posts(id) ON DELETE SET NULL,
            reporter_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            bot_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            issue_type VARCHAR(20) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'open',
            title VARCHAR(255) NOT NULL,
            resolution_note TEXT,
            resolved_by UUID REFERENCES entities(id) ON DELETE SET NULL,
            resolved_at TIMESTAMPTZ,
            resolution_reply_id UUID REFERENCES posts(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_issue_reports_status "
        "ON issue_reports(status)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_issue_reports_reporter "
        "ON issue_reports(reporter_entity_id)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_issue_reports_type_status "
        "ON issue_reports(issue_type, status)"
    ))


def downgrade() -> None:
    op.drop_table("issue_reports")
    op.drop_column("notification_preferences", "email_notifications_enabled")
