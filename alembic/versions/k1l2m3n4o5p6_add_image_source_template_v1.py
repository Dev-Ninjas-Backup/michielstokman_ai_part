"""Add template_v1 to the imagesource enum for HTML cover_template covers.

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-09-12 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "k1l2m3n4o5p6"
down_revision: Union[str, Sequence[str], None] = "j0k1l2m3n4o5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres enum: add value for COVER_GENERATION_METHOD=template covers.
    op.execute("ALTER TYPE imagesource ADD VALUE IF NOT EXISTS 'template_v1'")


def downgrade() -> None:
    # Postgres cannot easily drop enum values; leave template_v1 in place.
    # Rows using it should be cleared before a hard downgrade if ever needed.
    pass
