"""add image_url to day definition

Revision ID: a2c3d4e5f6b7
Revises: 474b5bc07d6f
Create Date: 2026-05-21 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2c3d4e5f6b7'
down_revision: Union[str, Sequence[str], None] = '2260ebd3a9d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('liberation_day_definitions', sa.Column('image_url', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('liberation_day_definitions', 'image_url')
