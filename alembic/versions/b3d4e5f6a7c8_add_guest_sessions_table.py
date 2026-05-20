"""add guest_sessions table

Revision ID: b3d4e5f6a7c8
Revises: a2c3d4e5f6b7
Create Date: 2026-05-21 03:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b3d4e5f6a7c8'
down_revision: Union[str, Sequence[str], None] = 'a2c3d4e5f6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the guest_sessions table."""
    op.create_table(
        'guest_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('last_story_date', sa.Date(), nullable=True),
        sa.Column('last_story_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    """Drop the guest_sessions table."""
    op.drop_table('guest_sessions')
