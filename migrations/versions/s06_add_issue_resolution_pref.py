"""Add issue_resolution_enabled to notification_preferences.

Revision ID: s06_issue_resolution_pref
Revises: s05_issue_reports_email_notif
Create Date: 2026-03-12 18:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "s06_issue_resolution_pref"
down_revision = "s05_issue_reports_email_notif"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE notification_preferences "
        "ADD COLUMN IF NOT EXISTS issue_resolution_enabled BOOLEAN DEFAULT TRUE"
    ))


def downgrade() -> None:
    op.drop_column("notification_preferences", "issue_resolution_enabled")
