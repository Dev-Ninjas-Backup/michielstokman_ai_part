"""add_bio_and_rename_freedom_slider

Revision ID: e898c509cede
Revises: 61c16e7f0f9a
Create Date: 2026-05-13 02:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e898c509cede'
down_revision: Union[str, Sequence[str], None] = '61c16e7f0f9a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Add bio column
    op.add_column('user_profiles', sa.Column('bio', sa.String(), nullable=True))
    # 2. Rename slider_free_freedom to slider_fear_freedom
    op.alter_column('user_profiles', 'slider_free_freedom', new_column_name='slider_fear_freedom')

def downgrade() -> None:
    op.alter_column('user_profiles', 'slider_fear_freedom', new_column_name='slider_free_freedom')
    op.drop_column('user_profiles', 'bio')
