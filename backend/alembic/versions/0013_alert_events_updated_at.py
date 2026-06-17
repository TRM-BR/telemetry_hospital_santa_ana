"""0013_alert_events_updated_at — Adiciona updated_at em alert_events.

alert_events era insert-only. Com esta coluna, o worker pode atualizar o
evento ativo a cada ciclo (ramo 'sustained') sem perder triggered_at.

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alert_events",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_column("alert_events", "updated_at")
