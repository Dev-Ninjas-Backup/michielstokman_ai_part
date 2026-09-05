"""add per-asset review statuses and published_at

Revision ID: g7h8i9j0k1l2
Revises: d2e3f4a5b6c7
Create Date: 2026-09-05 10:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g7h8i9j0k1l2"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

asset_status = sa.Enum(
    "missing",
    "pending",
    "in_progress",
    "ready_for_review",
    "approved",
    "rejected",
    name="assetreviewstatus",
)


def upgrade() -> None:
    bind = op.get_bind()
    asset_status.create(bind, checkfirst=True)
    op.add_column(
        "stories",
        sa.Column(
            "content_status",
            asset_status,
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "stories",
        sa.Column(
            "cover_status",
            asset_status,
            nullable=False,
            server_default="missing",
        ),
    )
    op.add_column(
        "stories",
        sa.Column(
            "voice_status",
            asset_status,
            nullable=False,
            server_default="missing",
        ),
    )
    op.add_column(
        "stories",
        sa.Column(
            "voice_not_required",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column("stories", sa.Column("published_at", sa.DateTime(), nullable=True))

    op.execute(
        """
        UPDATE stories
        SET
            content_status = CASE
                WHEN moderation_status = 'approved' THEN 'approved'
                WHEN generation_status = 'processing' THEN 'in_progress'
                WHEN story_text IS NOT NULL AND btrim(story_text) <> '' THEN 'ready_for_review'
                ELSE 'missing'
            END::assetreviewstatus,
            cover_status = CASE
                WHEN moderation_status = 'approved' AND cover_image_url IS NOT NULL AND btrim(cover_image_url) <> '' THEN 'approved'
                WHEN cover_image_url IS NOT NULL AND btrim(cover_image_url) <> '' THEN 'ready_for_review'
                ELSE 'missing'
            END::assetreviewstatus,
            voice_status = CASE
                WHEN audio_path IS NULL OR btrim(audio_path) = '' THEN
                    CASE WHEN moderation_status = 'approved' THEN 'approved' ELSE 'missing' END
                WHEN moderation_status = 'approved' THEN 'approved'
                ELSE 'ready_for_review'
            END::assetreviewstatus,
            voice_not_required = CASE
                WHEN moderation_status = 'approved' AND (audio_path IS NULL OR btrim(audio_path) = '') THEN true
                ELSE false
            END,
            published_at = CASE
                WHEN moderation_status = 'approved' THEN COALESCE(moderation_reviewed_at, updated_at, created_at)
                ELSE NULL
            END
        """
    )


def downgrade() -> None:
    op.drop_column("stories", "published_at")
    op.drop_column("stories", "voice_not_required")
    op.drop_column("stories", "voice_status")
    op.drop_column("stories", "cover_status")
    op.drop_column("stories", "content_status")
    asset_status.drop(op.get_bind(), checkfirst=True)
