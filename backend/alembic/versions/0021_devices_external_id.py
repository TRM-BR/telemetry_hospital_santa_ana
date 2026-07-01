"""Add external_id to devices for non-IMEI meters (SM-3EGW).

SM-3EGW se identifica pelo campo "id" do payload (ex.: "iemedidor"),
não por IMEI numérico. Esta migration adiciona external_id para cobrir
esse caso sem tornar imei nullable (preserva autodetect do SN50/DTN).

Estratégia:
  - external_id VARCHAR(64) NULL — opcional; SN50 nunca usa.
  - Índice unique parcial WHERE external_id IS NOT NULL — NULL não viola o unique.
  - imei continua UNIQUE NOT NULL — sem regressão no autodetect.

Idempotência:
  - ADD COLUMN IF NOT EXISTS em todos os campos — label e status podem já
    existir no banco de hml se foram adicionados manualmente ou por outro path.
  - CREATE UNIQUE INDEX IF NOT EXISTS no índice de external_id.

Downgrade:
  - Remove apenas external_id (coluna nova introduzida por esta migration) e
    o índice novo. label e status NÃO são dropados no downgrade porque podem
    ser preexistentes no schema; dropar seria destrutivo sem garantia de origem.

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
    # ADD COLUMN IF NOT EXISTS — seguro se a coluna já existir por qualquer motivo.
    op.execute(
        "ALTER TABLE devices ADD COLUMN IF NOT EXISTS external_id VARCHAR(64) NULL;"
    )
    op.execute(
        "ALTER TABLE devices ADD COLUMN IF NOT EXISTS label VARCHAR(128) NULL;"
    )
    op.execute(
        "ALTER TABLE devices ADD COLUMN IF NOT EXISTS status VARCHAR(32) NULL;"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_devices_external_id
        ON devices (external_id)
        WHERE external_id IS NOT NULL;
        """
    )


def downgrade() -> None:
    # Remove apenas o que esta migration introduziu de forma inequívoca.
    # label e status são omitidos: podem ser preexistentes e dropar seria destrutivo.
    op.execute("DROP INDEX IF EXISTS uq_devices_external_id;")
    op.execute("ALTER TABLE devices DROP COLUMN IF EXISTS external_id;")
