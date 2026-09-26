"""Add template_v2 to the imagesource enum for V2 cover generation.

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-09-26 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "l2m3n4o5p6q7"
down_revision: Union[str, Sequence[str], None] = "k1l2m3n4o5p6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres enum: add value for COVER_GENERATION_METHOD=v2 covers.
    op.execute("ALTER TYPE imagesource ADD VALUE IF NOT EXISTS 'template_v2'")


def downgrade() -> None:
    # Postgres cannot easily drop enum values; leave template_v2 in place.
    pass
