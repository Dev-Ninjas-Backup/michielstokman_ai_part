"""Align user-owned FKs for hard-delete cascade wipe.

Owned rows (profile, oauth, credits, subscriptions, payments, journeys) CASCADE
when a user is deleted. Shared catalog refs (liberation creator/reviewer, cover
uploader) SET NULL so products stay. Stories stay SET NULL at the DB layer;
application code wipes owned stories (and media) before deleting the user.

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-09-07 09:40:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "i9j0k1l2m3n4"
down_revision: Union[str, Sequence[str], None] = "h8i9j0k1l2m3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_fk(table: str, column: str) -> None:
    """Drop whatever FK currently points from table.column to users.id."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT tc.constraint_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_name = :table
              AND kcu.column_name = :column
              AND ccu.table_name = 'users'
            """
        ),
        {"table": table, "column": column},
    ).fetchall()
    for (name,) in rows:
        op.drop_constraint(name, table, type_="foreignkey")


def upgrade() -> None:
    # Owned data — wipe with the user
    for table, column, name in (
        ("user_profiles", "user_id", "fk_user_profiles_user_id_cascade"),
        ("user_oauth_accounts", "user_id", "fk_user_oauth_accounts_user_id_cascade"),
        ("user_subscriptions", "user_id", "fk_user_subscriptions_user_id_cascade"),
        ("payment_transactions", "user_id", "fk_payment_transactions_user_id_cascade"),
        ("user_journeys", "user_id", "fk_user_journeys_user_id_cascade"),
    ):
        _drop_fk(table, column)
        op.create_foreign_key(
            name,
            table,
            "users",
            [column],
            ["id"],
            ondelete="CASCADE",
        )

    # Shared catalog — keep the row, clear the admin pointer
    op.alter_column(
        "liberation_definitions",
        "created_by",
        existing_type=sa.UUID(),
        nullable=True,
    )
    for table, column, name in (
        ("liberation_definitions", "created_by", "fk_liberation_definitions_created_by_set_null"),
        ("liberation_definitions", "reviewed_by", "fk_liberation_definitions_reviewed_by_set_null"),
        ("cover_images", "uploaded_by", "fk_cover_images_uploaded_by_set_null"),
    ):
        _drop_fk(table, column)
        op.create_foreign_key(
            name,
            table,
            "users",
            [column],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    for table, column, name in (
        ("cover_images", "uploaded_by", "fk_cover_images_uploaded_by_set_null"),
        ("liberation_definitions", "reviewed_by", "fk_liberation_definitions_reviewed_by_set_null"),
        ("liberation_definitions", "created_by", "fk_liberation_definitions_created_by_set_null"),
    ):
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(None, table, "users", [column], ["id"])

    # Restore NOT NULL on created_by only when every row still has a creator
    op.execute(
        "UPDATE liberation_definitions SET created_by = reviewed_by "
        "WHERE created_by IS NULL AND reviewed_by IS NOT NULL"
    )
    op.alter_column(
        "liberation_definitions",
        "created_by",
        existing_type=sa.UUID(),
        nullable=False,
    )

    for table, column, name in (
        ("user_journeys", "user_id", "fk_user_journeys_user_id_cascade"),
        ("payment_transactions", "user_id", "fk_payment_transactions_user_id_cascade"),
        ("user_subscriptions", "user_id", "fk_user_subscriptions_user_id_cascade"),
        ("user_oauth_accounts", "user_id", "fk_user_oauth_accounts_user_id_cascade"),
        ("user_profiles", "user_id", "fk_user_profiles_user_id_cascade"),
    ):
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(None, table, "users", [column], ["id"])
