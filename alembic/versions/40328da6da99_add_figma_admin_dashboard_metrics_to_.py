"""add_figma_admin_dashboard_metrics_to_stories

Revision ID: 40328da6da99
Revises: 947dc7baf269
Create Date: 2026-05-12 03:31:43.427627

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '40328da6da99'
down_revision: Union[str, Sequence[str], None] = '947dc7baf269'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('stories', sa.Column('views_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('stories', sa.Column('shares_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('stories', sa.Column('pulse_score', sa.Float(), nullable=False, server_default='0.0'))
    op.add_column('stories', sa.Column('reflections_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('stories', 'reflections_count')
    op.drop_column('stories', 'pulse_score')
    op.drop_column('stories', 'shares_count')
    op.drop_column('stories', 'views_count')
