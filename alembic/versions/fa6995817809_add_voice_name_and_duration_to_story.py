"""add_voice_name_and_duration_to_story

Revision ID: fa6995817809
Revises: 7a8fddfcc85d
Create Date: 2026-05-12 04:08:21.627100

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fa6995817809'
down_revision: Union[str, Sequence[str], None] = '7a8fddfcc85d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('stories', sa.Column('voice_name', sa.String(), nullable=True))
    op.add_column('stories', sa.Column('audio_duration_seconds', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('stories', 'audio_duration_seconds')
    op.drop_column('stories', 'voice_name')
