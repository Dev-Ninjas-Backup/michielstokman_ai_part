"""add submission_mode and character brief fields

Revision ID: a9b8c7d6e5f4
Revises: f1a2b3c4d5e6
Create Date: 2026-08-29 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a9b8c7d6e5f4"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

submission_mode_enum = sa.Enum("studio", "human_ready", name="submissionmode")


def upgrade() -> None:
    submission_mode_enum.create(op.get_bind(), checkfirst=True)
    op.add_column("stories", sa.Column("sexual_orientation", sa.String(), nullable=True))
    op.add_column("stories", sa.Column("background", sa.Text(), nullable=True))
    op.add_column("stories", sa.Column("personality", sa.Text(), nullable=True))
    op.add_column("stories", sa.Column("lifestyle", sa.Text(), nullable=True))
    op.add_column("stories", sa.Column("situation", sa.Text(), nullable=True))
    op.add_column(
        "stories",
        sa.Column(
            "submission_mode",
            submission_mode_enum,
            nullable=False,
            server_default="studio",
        ),
    )


def downgrade() -> None:
    op.drop_column("stories", "submission_mode")
    op.drop_column("stories", "situation")
    op.drop_column("stories", "lifestyle")
    op.drop_column("stories", "personality")
    op.drop_column("stories", "background")
    op.drop_column("stories", "sexual_orientation")
    submission_mode_enum.drop(op.get_bind(), checkfirst=True)
