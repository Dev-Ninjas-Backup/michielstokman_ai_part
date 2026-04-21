"""Add cover_images table and cover_image_url to stories

Revision ID: a1b2c3d4e5f6
Revises: 08012d02811d
Create Date: 2026-04-22 00:07:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '8427782400d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create cover_images table
    op.create_table(
        'cover_images',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column(
            'story_type',
            sa.Enum('confession', 'meditation', 'transformation', name='coverimagetype'),
            nullable=False,
        ),
        sa.Column('image_url', sa.String(), nullable=False),
        sa.Column('s3_key', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('uploaded_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_cover_images_story_type'), 'cover_images', ['story_type'], unique=False)
    op.create_index(op.f('ix_cover_images_is_active'), 'cover_images', ['is_active'], unique=False)
    op.create_index(op.f('ix_cover_images_uploaded_by'), 'cover_images', ['uploaded_by'], unique=False)

    # Add cover_image_url column to stories table
    op.add_column(
        'stories',
        sa.Column('cover_image_url', sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove cover_image_url from stories
    op.drop_column('stories', 'cover_image_url')

    # Drop cover_images table and its indexes
    op.drop_index(op.f('ix_cover_images_uploaded_by'), table_name='cover_images')
    op.drop_index(op.f('ix_cover_images_is_active'), table_name='cover_images')
    op.drop_index(op.f('ix_cover_images_story_type'), table_name='cover_images')
    op.drop_table('cover_images')
    op.execute("DROP TYPE IF EXISTS coverimagetype")
