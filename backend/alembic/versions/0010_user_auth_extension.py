"""0010_user_auth_extension — Extensão do sistema de autenticação.

Adiciona:
  - users.account_status (VARCHAR 24, default 'active')
  - users.requested_role (VARCHAR 20, nullable)
  - Tabela email_codes (OTP para signup, reset de senha, troca de email)
  - Tabela user_approvals (votos de aprovação de cadastro)

Usuários existentes com email NULL recebem account_status='pending_email_change'
para indicar que precisam cadastrar um email; os demais ficam 'active'.

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Alterações em users ───────────────────────────────────────────────────
    op.add_column(
        "users",
        sa.Column(
            "account_status",
            sa.String(24),
            nullable=False,
            server_default="'active'",
        ),
    )
    op.add_column(
        "users",
        sa.Column("requested_role", sa.String(20), nullable=True),
    )

    # Usuários que não têm email ficam em pending_email_change
    op.execute(
        "UPDATE users SET account_status = 'pending_email_change' WHERE email IS NULL"
    )

    # Índice único case-insensitive para email (busca por identifier)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_lower "
        "ON users (lower(email)) WHERE email IS NOT NULL"
    )

    # Adiciona 'approver' ao check constraint de role
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT ck_users_role "
        "CHECK (role IN ('admin', 'operador', 'viewer', 'approver'))"
    )

    # ── Tabela email_codes ────────────────────────────────────────────────────
    op.create_table(
        "email_codes",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("code_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "attempts",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("pending_payload", JSONB, nullable=True),
    )
    op.create_index("ix_email_codes_user_id", "email_codes", ["user_id"])
    op.create_index("ix_email_codes_email_purpose", "email_codes", ["email", "purpose"])

    # ── Tabela user_approvals ─────────────────────────────────────────────────
    op.create_table(
        "user_approvals",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "target_user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "approver_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("target_user_id", "approver_id", name="uq_user_approval_vote"),
    )
    op.create_index(
        "ix_user_approvals_target", "user_approvals", ["target_user_id"]
    )


def downgrade() -> None:
    op.drop_table("user_approvals")
    op.drop_table("email_codes")
    op.execute("DROP INDEX IF EXISTS uq_users_email_lower")
    op.drop_column("users", "requested_role")
    op.drop_column("users", "account_status")
    # Restaura constraint sem 'approver'
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT ck_users_role "
        "CHECK (role IN ('admin', 'operador', 'viewer'))"
    )
