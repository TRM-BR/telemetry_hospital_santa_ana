"""Suporta múltiplos ids de Telegram por user e garante 1 envio por id por alerta.

user_telegram_links: troca UNIQUE(user_id) por UNIQUE(user_id, telegram_chat_id).
alert_notifications: troca UNIQUE(event,user,channel) por UNIQUE(event,channel,dest).

Revision ID: 0015
Revises: 0014
"""
from __future__ import annotations

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_user_telegram_links_user",
        "user_telegram_links",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_user_telegram_links_user_chat",
        "user_telegram_links",
        ["user_id", "telegram_chat_id"],
    )

    op.drop_constraint(
        "uq_alert_notification_event_user_channel",
        "alert_notifications",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_alert_notification_event_channel_dest",
        "alert_notifications",
        ["alert_event_id", "channel", "destination_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_alert_notification_event_channel_dest",
        "alert_notifications",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_alert_notification_event_user_channel",
        "alert_notifications",
        ["alert_event_id", "user_id", "channel"],
    )

    op.drop_constraint(
        "uq_user_telegram_links_user_chat",
        "user_telegram_links",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_user_telegram_links_user",
        "user_telegram_links",
        ["user_id"],
    )
