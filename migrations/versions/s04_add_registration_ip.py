"""Add entities.registration_ip column for Sybil cluster detection.

Stores the client IP at registration time so the population safety
detector can identify clusters of entities created from the same address.

Revision ID: s04_registration_ip
Revises: s03_missing_columns
Create Date: 2026-03-09 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "s04_registration_ip"
down_revision = "s03_missing_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE entities ADD COLUMN IF NOT EXISTS "
        "registration_ip VARCHAR(45)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_entities_registration_ip "
        "ON entities (registration_ip)"
    ))


def downgrade() -> None:
    op.drop_index("ix_entities_registration_ip", table_name="entities")
    op.drop_column("entities", "registration_ip")
