"""Restaura lat/lng e adiciona group_name em installations.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-21

lat/lng foram removidas em 0003. São necessárias para o mapa Leaflet do front.
group_name permite agrupar instalações no menu (ex.: "Parque" para parque_caixa
e parque_entrada). NULL = aparece no nível raiz.

Seeds de grupo para Barueri:
  parque_caixa    → group_name = 'Parque'
  parque_entrada  → group_name = 'Parque'
  escola          → NULL
  secretaria_construcao → NULL
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("installations", sa.Column("lat",        sa.Float(), nullable=True))
    op.add_column("installations", sa.Column("lng",        sa.Float(), nullable=True))
    op.add_column("installations", sa.Column("group_name", sa.String(64), nullable=True))

    # Seed de grupo para Barueri
    op.execute("""
        UPDATE installations
        SET group_name = 'Parque'
        WHERE slug IN ('parque_caixa', 'parque_entrada');
    """)


def downgrade() -> None:
    op.drop_column("installations", "group_name")
    op.drop_column("installations", "lng")
    op.drop_column("installations", "lat")
