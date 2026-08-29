"""restore human_ready story_text from story_input

Revision ID: c1d2e3f4a5b6
Revises: a9b8c7d6e5f4
Create Date: 2026-08-29 17:10:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "a9b8c7d6e5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Fully narrated rows were rewritten while the uploaded audio was kept.
    # story_input is still the member's script — publish that as story_text.
    op.execute(
        """
        UPDATE stories
        SET story_text = story_input
        WHERE submission_mode = 'human_ready'
          AND story_input IS NOT NULL
          AND btrim(story_input) <> ''
          AND (story_text IS NULL OR story_text IS DISTINCT FROM story_input)
        """
    )


def downgrade() -> None:
    # Rewritten copy was overwritten; it cannot be restored.
    pass
