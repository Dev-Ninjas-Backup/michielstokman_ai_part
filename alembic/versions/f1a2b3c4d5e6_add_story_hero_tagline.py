"""add hero_tagline for details brush copy

Revision ID: f1a2b3c4d5e6
Revises: e8a1c2d3f4b5
Create Date: 2026-08-29 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e8a1c2d3f4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stories", sa.Column("hero_tagline", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("stories", "hero_tagline")
