"""Widen topic columns from varchar(100) to varchar(200).

LLM-generated campaign topic names can exceed 100 chars.

Revision ID: s17_topic
Revises: s16_recruit
"""
from __future__ import annotations

from alembic import op

revision = "s17_topic"
down_revision = "s16_recruit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "marketing_campaigns", "topic",
        type_=__import__("sqlalchemy").String(200),
        existing_type=__import__("sqlalchemy").String(100),
        existing_nullable=False,
    )
    op.alter_column(
        "marketing_posts", "topic",
        type_=__import__("sqlalchemy").String(200),
        existing_type=__import__("sqlalchemy").String(100),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "marketing_posts", "topic",
        type_=__import__("sqlalchemy").String(100),
        existing_type=__import__("sqlalchemy").String(200),
        existing_nullable=True,
    )
    op.alter_column(
        "marketing_campaigns", "topic",
        type_=__import__("sqlalchemy").String(100),
        existing_type=__import__("sqlalchemy").String(200),
        existing_nullable=False,
    )
