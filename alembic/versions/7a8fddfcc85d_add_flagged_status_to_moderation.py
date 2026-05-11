"""add_flagged_status_to_moderation

Revision ID: 7a8fddfcc85d
Revises: 40328da6da99
Create Date: 2026-05-12 03:56:07.052295

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a8fddfcc85d'
down_revision: Union[str, Sequence[str], None] = '40328da6da99'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use execute to alter the enum type in postgres
    # Note: postgres doesn't support removing values from an enum easily, so downgrade does nothing.
    # In a real environment, we use COMMIT because ALTER TYPE cannot run in a transaction block
    op.execute("COMMIT")
    op.execute("ALTER TYPE moderationstatus ADD VALUE IF NOT EXISTS 'flagged'")


def downgrade() -> None:
    pass
