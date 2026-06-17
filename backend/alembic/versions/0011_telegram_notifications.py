"""0011_telegram_notifications — Integração Telegram para alertas críticos.

Adiciona:
  - user_telegram_links               — vínculo user_id ↔ telegram_chat_id
  - telegram_link_tokens              — tokens temporários de vínculo (só hash)
  - user_alert_notification_preferences — preferências de notificação por usuário
  - alert_notifications               — fila/log de notificações (envio assíncrono)

FKs para users/installations/alert_events usam sa.Integer (PKs referenciadas
são int4, como em email_codes). PKs próprias são BigInteger; telegram_chat_id
é BigInteger (ids de chat do Telegram excedem int4).

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── user_telegram_links ───────────────────────────────────────────────────
    op.create_table(
        "user_telegram_links",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("telegram_chat_id", sa.BigInteger, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger, nullable=True),
        sa.Column("telegram_username", sa.String(255), nullable=True),
        sa.Column("telegram_first_name", sa.String(255), nullable=True),
        sa.Column("telegram_last_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("unlinked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", name="uq_user_telegram_links_user"),
        sa.UniqueConstraint("telegram_chat_id", name="uq_user_telegram_links_chat"),
    )

    # ── telegram_link_tokens ──────────────────────────────────────────────────
    op.create_table(
        "telegram_link_tokens",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.Text, nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_telegram_link_tokens_user_id", "telegram_link_tokens", ["user_id"]
    )

    # ── user_alert_notification_preferences ───────────────────────────────────
    op.create_table(
        "user_alert_notification_preferences",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "channel", sa.String(32), nullable=False, server_default="'telegram'"
        ),
        sa.Column(
            "enabled", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "min_severity", sa.String(32), nullable=False, server_default="'critical'"
        ),
        sa.Column(
            "installation_id",
            sa.Integer,
            sa.ForeignKey("installations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("alert_type", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_user_alert_notif_prefs_user_id",
        "user_alert_notification_preferences",
        ["user_id"],
    )

    # ── alert_notifications ───────────────────────────────────────────────────
    op.create_table(
        "alert_notifications",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "alert_event_id",
            sa.Integer,
            sa.ForeignKey("alert_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "channel", sa.String(32), nullable=False, server_default="'telegram'"
        ),
        sa.Column(
            "destination_type",
            sa.String(32),
            nullable=False,
            server_default="'user'",
        ),
        sa.Column("destination_id", sa.Text, nullable=False),
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="'pending'"
        ),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="5"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("provider_message_id", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "alert_event_id",
            "user_id",
            "channel",
            name="uq_alert_notification_event_user_channel",
        ),
    )
    # Índice parcial para a varredura do worker (fila pendente/retry devida).
    op.create_index(
        "ix_alert_notifications_due",
        "alert_notifications",
        ["next_retry_at"],
        postgresql_where=sa.text("status IN ('pending', 'retry')"),
    )


def downgrade() -> None:
    op.drop_index("ix_alert_notifications_due", table_name="alert_notifications")
    op.drop_table("alert_notifications")
    op.drop_index(
        "ix_user_alert_notif_prefs_user_id",
        table_name="user_alert_notification_preferences",
    )
    op.drop_table("user_alert_notification_preferences")
    op.drop_index(
        "ix_telegram_link_tokens_user_id", table_name="telegram_link_tokens"
    )
    op.drop_table("telegram_link_tokens")
    op.drop_table("user_telegram_links")
