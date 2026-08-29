"""add public story identity fields and hero hook

Revision ID: e8a1c2d3f4b5
Revises: d4e5f6a7b8c9
Create Date: 2026-08-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e8a1c2d3f4b5"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stories", sa.Column("location", sa.String(), nullable=True))
    op.add_column("stories", sa.Column("gender", sa.String(), nullable=True))
    op.add_column("stories", sa.Column("occupation", sa.String(), nullable=True))
    op.add_column("stories", sa.Column("age", sa.Integer(), nullable=True))
    op.add_column("stories", sa.Column("hero_hook", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("stories", "hero_hook")
    op.drop_column("stories", "age")
    op.drop_column("stories", "occupation")
    op.drop_column("stories", "gender")
    op.drop_column("stories", "location")
