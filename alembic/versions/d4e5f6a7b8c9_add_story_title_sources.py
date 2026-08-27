"""add member and AI story title sources

Revision ID: d4e5f6a7b8c9
Revises: c7f1a9b2d4e3
Create Date: 2026-08-27 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c7f1a9b2d4e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stories", sa.Column("member_title", sa.String(), nullable=True))
    op.add_column("stories", sa.Column("ai_generated_title", sa.String(), nullable=True))
    op.add_column(
        "stories",
        sa.Column(
            "use_ai_title",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Existing rows: treat current title as the member's chosen title.
    op.execute(
        """
        UPDATE stories
        SET member_title = title
        WHERE title IS NOT NULL AND TRIM(title) <> ''
        """
    )

    op.alter_column("stories", "use_ai_title", server_default=None)


def downgrade() -> None:
    op.drop_column("stories", "use_ai_title")
    op.drop_column("stories", "ai_generated_title")
    op.drop_column("stories", "member_title")
