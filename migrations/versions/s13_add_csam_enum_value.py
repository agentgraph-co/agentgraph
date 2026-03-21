"""Add CSAM value to moderationreason Postgres enum.

The Python ModerationReason enum has had CSAM since inception but the
initial migration never included it in the Postgres enum type.

Revision ID: s13_csam_enum
Revises: s12_search_trgm
Create Date: 2026-03-20
"""
from __future__ import annotations

from alembic import op

revision = "s13_csam_enum"
down_revision = "s12_search_trgm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add CSAM to the moderationreason enum type
    # Must use raw SQL — Alembic has no built-in ALTER TYPE support
    op.execute("ALTER TYPE moderationreason ADD VALUE IF NOT EXISTS 'CSAM'")


def downgrade() -> None:
    # Postgres does not support removing enum values directly.
    # This is a no-op; the value will remain harmlessly if downgraded.
    pass
