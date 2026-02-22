"""Add sso_provider_id to entities for SSO login tracking

Revision ID: i09_sso_config
Revises: i08_anomaly_alerts
Create Date: 2026-02-21 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "i09_sso_config"
down_revision = "i08_anomaly_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "entities",
        sa.Column("sso_provider_id", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("entities", "sso_provider_id")
