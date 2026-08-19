"""add member story management fields

Adds member-facing story management support:
  - human-readable story_number backed by a Postgres sequence
  - member submission lifecycle (submitted / withdrawn) + regeneration counter
  - explicit voice selection, including cloned member voices
  - cover image provenance and storage key
  - per-platform social intro copy for Meta and Spotify
  - cloned voice reference on the user profile

Revision ID: c7f1a9b2d4e3
Revises: 8b969ee877fd
Create Date: 2026-08-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c7f1a9b2d4e3'
down_revision: Union[str, Sequence[str], None] = '8b969ee877fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SUBMISSION_STATUS = postgresql.ENUM(
    'draft', 'submitted', 'withdrawn',
    name='submissionstatus',
    create_type=False,
)
IMAGE_SOURCE = postgresql.ENUM(
    'ai_generated', 'user_uploaded', 'admin_default',
    name='imagesource',
    create_type=False,
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    SUBMISSION_STATUS.create(bind, checkfirst=True)
    IMAGE_SOURCE.create(bind, checkfirst=True)

    # --- Human-readable story number -------------------------------------
    # The sequence is created without an owner column so the backfill below can
    # assign numbers to existing rows before the default starts firing.
    op.execute("CREATE SEQUENCE IF NOT EXISTS story_number_seq START WITH 1 INCREMENT BY 1")
    op.add_column('stories', sa.Column('story_number', sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE stories AS s
        SET story_number = numbered.rn
        FROM (
            SELECT id, row_number() OVER (ORDER BY created_at, id) AS rn
            FROM stories
        ) AS numbered
        WHERE s.id = numbered.id
        """
    )
    # Advance the sequence past the backfilled range so new rows never collide.
    op.execute(
        """
        SELECT setval(
            'story_number_seq',
            COALESCE((SELECT MAX(story_number) FROM stories), 0) + 1,
            false
        )
        """
    )
    op.alter_column(
        'stories',
        'story_number',
        server_default=sa.text("nextval('story_number_seq')"),
    )
    op.create_index('ix_stories_story_number', 'stories', ['story_number'], unique=True)

    # --- Voice selection --------------------------------------------------
    op.add_column('stories', sa.Column('voice_id', sa.String(), nullable=True))
    op.add_column(
        'stories',
        sa.Column('uses_custom_voice', sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # --- Cover image provenance ------------------------------------------
    op.add_column('stories', sa.Column('cover_image_key', sa.String(), nullable=True))
    op.add_column('stories', sa.Column('image_source', IMAGE_SOURCE, nullable=True))
    # Existing rows already carry a cover assigned by the AI pipeline or admin defaults.
    op.execute(
        "UPDATE stories SET image_source = 'admin_default' WHERE cover_image_url IS NOT NULL"
    )

    # --- Social distribution copy ----------------------------------------
    op.add_column(
        'stories',
        sa.Column('social_intros', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column('stories', sa.Column('social_intros_generated_at', sa.DateTime(), nullable=True))

    # --- Member submission lifecycle --------------------------------------
    op.add_column(
        'stories',
        sa.Column(
            'submission_status',
            SUBMISSION_STATUS,
            nullable=False,
            server_default='submitted',
        ),
    )
    op.add_column('stories', sa.Column('withdrawn_at', sa.DateTime(), nullable=True))
    op.add_column(
        'stories',
        sa.Column('regeneration_count', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index('ix_stories_submission_status', 'stories', ['submission_status'])

    # --- Cloned voice on the profile --------------------------------------
    op.add_column('user_profiles', sa.Column('custom_voice_id', sa.String(), nullable=True))
    op.add_column('user_profiles', sa.Column('custom_voice_name', sa.String(), nullable=True))
    op.add_column('user_profiles', sa.Column('custom_voice_created_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('user_profiles', 'custom_voice_created_at')
    op.drop_column('user_profiles', 'custom_voice_name')
    op.drop_column('user_profiles', 'custom_voice_id')

    op.drop_index('ix_stories_submission_status', table_name='stories')
    op.drop_column('stories', 'regeneration_count')
    op.drop_column('stories', 'withdrawn_at')
    op.drop_column('stories', 'submission_status')

    op.drop_column('stories', 'social_intros_generated_at')
    op.drop_column('stories', 'social_intros')

    op.drop_column('stories', 'image_source')
    op.drop_column('stories', 'cover_image_key')

    op.drop_column('stories', 'uses_custom_voice')
    op.drop_column('stories', 'voice_id')

    op.drop_index('ix_stories_story_number', table_name='stories')
    op.drop_column('stories', 'story_number')
    op.execute("DROP SEQUENCE IF EXISTS story_number_seq")

    bind = op.get_bind()
    IMAGE_SOURCE.drop(bind, checkfirst=True)
    SUBMISSION_STATUS.drop(bind, checkfirst=True)
