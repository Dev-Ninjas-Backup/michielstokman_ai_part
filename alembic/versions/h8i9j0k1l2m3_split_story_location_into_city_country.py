"""split story location into city and country

The publications dashboard edits city and country as separate fields. `location`
stays populated with the joined value so existing public responses keep working.

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-09-07 05:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, Sequence[str], None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stories", sa.Column("city", sa.String(), nullable=True))
    op.add_column("stories", sa.Column("country", sa.String(), nullable=True))

    # Split on the last comma: "Brooklyn, New York, USA" -> city "Brooklyn, New York",
    # country "USA". A value with no comma is treated as the city alone.
    op.execute(
        """
        UPDATE stories
        SET
            city = CASE
                WHEN position(',' in location) > 0 THEN
                    btrim(substring(
                        location from 1
                        for length(location) - position(',' in reverse(location))
                    ))
                ELSE btrim(location)
            END,
            country = CASE
                WHEN position(',' in location) > 0 THEN
                    btrim(substring(
                        location from length(location) - position(',' in reverse(location)) + 2
                    ))
                ELSE NULL
            END
        WHERE location IS NOT NULL AND btrim(location) <> ''
        """
    )

    # Blank strings left by a trailing comma are noise, not data.
    op.execute("UPDATE stories SET city = NULL WHERE btrim(coalesce(city, '')) = ''")
    op.execute("UPDATE stories SET country = NULL WHERE btrim(coalesce(country, '')) = ''")


def downgrade() -> None:
    op.drop_column("stories", "country")
    op.drop_column("stories", "city")
