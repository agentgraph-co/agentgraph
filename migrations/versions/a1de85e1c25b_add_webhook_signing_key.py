"""add_webhook_signing_key

Revision ID: a1de85e1c25b
Revises: 16779b10b997
Create Date: 2026-02-18 08:31:39.911334
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'a1de85e1c25b'
down_revision = '16779b10b997'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('webhook_subscriptions',
        sa.Column('signing_key', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('webhook_subscriptions', 'signing_key')
