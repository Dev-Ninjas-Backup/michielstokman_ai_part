"""merge heads

Revision ID: 61c16e7f0f9a
Revises: 497daa8c7544, fa6995817809
Create Date: 2026-05-12 04:13:19.457676

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '61c16e7f0f9a'
down_revision: Union[str, Sequence[str], None] = ('497daa8c7544', 'fa6995817809')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
