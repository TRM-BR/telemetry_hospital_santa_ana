"""0012_fix_min_severity_vocabulary — Alinha min_severity com vocabulário do sistema.

O valor 'critical' (inglês) foi inserido como default pela migration 0011 e pelo
link_service. O sistema usa 'critico' (português) em todo o restante do código.
Esta migration:
  1. Altera o server_default da coluna para 'critico'.
  2. Atualiza os registros existentes de 'critical' → 'critico'.

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Atualiza registros existentes gravados com o valor antigo.
    op.execute(
        sa.text(
            "UPDATE user_alert_notification_preferences "
            "SET min_severity = 'critico' "
            "WHERE min_severity = 'critical'"
        )
    )
    # Altera o server_default para novos registros criados diretamente via SQL.
    op.alter_column(
        "user_alert_notification_preferences",
        "min_severity",
        server_default="'critico'",
        existing_type=sa.String(32),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "user_alert_notification_preferences",
        "min_severity",
        server_default="'critical'",
        existing_type=sa.String(32),
        existing_nullable=False,
    )
    op.execute(
        sa.text(
            "UPDATE user_alert_notification_preferences "
            "SET min_severity = 'critical' "
            "WHERE min_severity = 'critico'"
        )
    )
