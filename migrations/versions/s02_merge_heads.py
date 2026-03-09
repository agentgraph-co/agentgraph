"""Merge s01_updated_at_indexes and s01_did_status into single head

Revision ID: s02_merge_heads
Revises: s01_updated_at_indexes, s01_did_status
Create Date: 2026-03-09 00:00:00.000000
"""
from __future__ import annotations

revision = "s02_merge_heads"
down_revision = ("s01_updated_at_indexes", "s01_did_status")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
