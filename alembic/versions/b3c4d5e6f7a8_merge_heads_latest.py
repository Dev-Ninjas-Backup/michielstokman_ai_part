"""merge heads latest

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f7, 3e1428ef72b7
Create Date: 2026-05-13 04:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = ('a1b2c3d4e5f7', '3e1428ef72b7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    pass

def downgrade() -> None:
    pass
