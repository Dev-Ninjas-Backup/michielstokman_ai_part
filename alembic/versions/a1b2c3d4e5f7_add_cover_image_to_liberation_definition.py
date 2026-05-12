"""add_cover_image_to_liberation_definition

Revision ID: a1b2c3d4e5f7
Revises: e898c509cede
Create Date: 2026-05-13 04:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, Sequence[str], None] = 'e898c509cede'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Add cover_image_url column to liberation_definitions
    op.add_column('liberation_definitions', sa.Column('cover_image_url', sa.String(), nullable=True))

def downgrade() -> None:
    op.drop_column('liberation_definitions', 'cover_image_url')
