"""Persist the resolved cover IMAGE_PROMPT on stories.

Stores the post-placeholder DALL-E prompt (without the Python identity lock)
so later cover jobs can reuse P1 instead of always rebuilding via P2.

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-09-08 12:24:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j0k1l2m3n4o5"
down_revision: Union[str, Sequence[str], None] = "i9j0k1l2m3n4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stories", sa.Column("image_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("stories", "image_prompt")
