"""Add external_id to devices for non-IMEI meters (SM-3EGW).

SM-3EGW se identifica pelo campo "id" do payload (ex.: "iemedidor"),
não por IMEI numérico. Esta migration adiciona external_id para cobrir
esse caso sem tornar imei nullable (preserva autodetect do SN50/DTN).

Estratégia:
  - external_id VARCHAR(64) NULL — opcional; SN50 nunca usa.
  - Índice unique parcial WHERE external_id IS NOT NULL — NULL não viola o unique.
  - imei continua UNIQUE NOT NULL — sem regressão no autodetect.

Revision ID: 0021
Revises: 0020
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("external_id", sa.String(64), nullable=True),
    )
    # Também adiciona label e status — campos usados no seed do SM-3EGW
    # e ausentes no modelo ORM atual (adicionados aqui para não criar migration extra).
    op.add_column(
        "devices",
        sa.Column("label", sa.String(128), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("status", sa.String(32), nullable=True),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_devices_external_id
        ON devices (external_id)
        WHERE external_id IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_devices_external_id")
    op.drop_column("devices", "status")
    op.drop_column("devices", "label")
    op.drop_column("devices", "external_id")
