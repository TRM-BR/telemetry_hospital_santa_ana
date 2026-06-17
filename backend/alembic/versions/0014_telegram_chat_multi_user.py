"""Permite que um mesmo telegram_chat_id vincule a múltiplos usuários.

Remove a constraint UNIQUE em telegram_chat_id: agora um telefone pode
receber notificações de quantas contas quiser. A unicidade por usuário
(uq_user_telegram_links_user) é mantida.

Revision ID: 0014
Revises: 0013
"""
from __future__ import annotations

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_user_telegram_links_chat",
        "user_telegram_links",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_user_telegram_links_chat",
        "user_telegram_links",
        ["telegram_chat_id"],
    )
