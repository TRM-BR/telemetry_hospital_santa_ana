"""Normalize account_status vocabulary.

Renames:
  pending_approval → pending
  active           → approved
  disabled         → inactive

Keeps reserved e-mail states: pending_email, pending_email_change.

Revision ID: 0019
Revises: 0018
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

# Canonical status values (+ reserved e-mail states)
_CANONICAL = "('pending','approved','rejected','inactive','pending_email','pending_email_change')"


def upgrade() -> None:
    # 1. Rename existing rows
    op.execute("UPDATE users SET account_status = 'pending'  WHERE account_status = 'pending_approval'")
    op.execute("UPDATE users SET account_status = 'approved' WHERE account_status = 'active'")
    op.execute("UPDATE users SET account_status = 'inactive' WHERE account_status = 'disabled'")

    # 2. Drop old CHECK constraint (may be named differently across envs — try both)
    with op.get_context().autocommit_block():
        op.execute(
            """
            DO $$
            DECLARE
                c TEXT;
            BEGIN
                FOR c IN
                    SELECT conname FROM pg_constraint
                    WHERE conrelid = 'users'::regclass AND contype = 'c'
                      AND conname ILIKE '%account_status%'
                LOOP
                    EXECUTE format('ALTER TABLE users DROP CONSTRAINT %I', c);
                END LOOP;
            END $$;
            """
        )

    # 3. Add new CHECK constraint
    op.create_check_constraint(
        "ck_users_account_status",
        "users",
        f"account_status IN {_CANONICAL}",
    )

    # 4. Update column default
    op.alter_column("users", "account_status", server_default="'approved'")


def downgrade() -> None:
    # Reverse renames
    op.execute("UPDATE users SET account_status = 'pending_approval' WHERE account_status = 'pending'")
    op.execute("UPDATE users SET account_status = 'active'           WHERE account_status = 'approved'")
    op.execute("UPDATE users SET account_status = 'disabled'         WHERE account_status = 'inactive'")

    # Drop new CHECK
    op.drop_constraint("ck_users_account_status", "users", type_="check")

    # Restore old default
    op.alter_column("users", "account_status", server_default="'active'")
