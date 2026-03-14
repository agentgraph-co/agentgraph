"""Add per-kind email preference columns to notification_preferences.

Revision ID: s07_per_kind_email_prefs
Revises: s06_issue_resolution_pref
Create Date: 2026-03-14 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "s07_per_kind_email_prefs"
down_revision = "s06_issue_resolution_pref"
branch_labels = None
depends_on = None

# (column_name, default_value)
_COLUMNS = [
    ("email_follow_enabled", "false"),
    ("email_vote_enabled", "false"),
    ("email_reply_enabled", "false"),
    ("email_mention_enabled", "true"),
    ("email_endorsement_enabled", "false"),
    ("email_review_enabled", "false"),
    ("email_moderation_enabled", "true"),
    ("email_message_enabled", "true"),
    ("email_issue_resolution_enabled", "true"),
]


def upgrade() -> None:
    conn = op.get_bind()
    for col, default in _COLUMNS:
        conn.execute(sa.text(
            f"ALTER TABLE notification_preferences "
            f"ADD COLUMN IF NOT EXISTS {col} BOOLEAN NOT NULL DEFAULT {default}"
        ))


def downgrade() -> None:
    for col, _ in _COLUMNS:
        op.drop_column("notification_preferences", col)
