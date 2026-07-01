"""Add installations.kind; seed Escola + SM-3EGW device (Santana do Parnaíba).

1. ALTER installations ADD COLUMN kind VARCHAR(16) NULL
     'hydraulic' = monitoramento hídrico (SN50/DTN)
     'energy'    = medidor de energia (SM-3EGW)
     NULL        = tipo não classificado (retrocompatível)

2. Backfill: hospital_santa_ana → 'hydraulic'

3. Seed (slug-guarded: só executa em santana_parnaiba):
   - installations: escola (kind='energy')
   - devices: SM-3EGW (imei='sm3egw-iemedidor', external_id='iemedidor')
       imei técnico controlado — nunca colide com IMEI real (15 dígitos).
       Identificador real do medidor = external_id='iemedidor'.
   - device_installations: vínculo escola ↔ SM-3EGW (valid_to=NULL = ativo)

Idempotente (ON CONFLICT DO NOTHING / DO UPDATE).

Revision ID: 0023
Revises: 0022
"""
from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

_TARGET_SLUG = "santana_parnaiba"


def _slug() -> str:
    return os.getenv("TELEMETRY_CLIENT_SLUG", "").strip() or _TARGET_SLUG


def upgrade() -> None:
    # ── 1. Coluna kind ────────────────────────────────────────────────────────
    op.add_column(
        "installations",
        sa.Column("kind", sa.String(16), nullable=True),
    )

    # ── 2. Backfill hospital_santa_ana → hydraulic ────────────────────────────
    op.execute(
        "UPDATE installations SET kind = 'hydraulic' WHERE slug = 'hospital_santa_ana' AND kind IS NULL"
    )

    if _slug() != _TARGET_SLUG:
        return

    conn = op.get_bind()

    # ── 3a. Instalação Escola ─────────────────────────────────────────────────
    conn.execute(
        sa.text("""
            INSERT INTO installations (
                slug, name, group_name, notes, kind, is_active, created_at, updated_at
            ) VALUES (
                'escola',
                'Escola Municipal',
                'Santana do Parnaíba',
                'Escola Municipal - Santana do Parnaíba/SP (medidor SM-3EGW)',
                'energy',
                true,
                now(),
                now()
            )
            ON CONFLICT (slug) DO UPDATE SET
                name        = EXCLUDED.name,
                group_name  = EXCLUDED.group_name,
                notes       = EXCLUDED.notes,
                kind        = EXCLUDED.kind,
                is_active   = EXCLUDED.is_active,
                updated_at  = now()
        """)
    )

    # ── 3b. Device SM-3EGW ────────────────────────────────────────────────────
    # imei = 'sm3egw-iemedidor': sentinel técnico controlado (nunca coincide com
    # IMEI real de 15 dígitos). O identificador real do medidor é external_id.
    conn.execute(
        sa.text("""
            INSERT INTO devices (
                imei, external_id, model, label, status, is_active, created_at
            ) VALUES (
                'sm3egw-iemedidor',
                'iemedidor',
                'SM-3EGW',
                'Medidor de Energia SM-3EGW',
                'active',
                true,
                now()
            )
            ON CONFLICT (imei) DO UPDATE SET
                external_id = EXCLUDED.external_id,
                model       = EXCLUDED.model,
                label       = EXCLUDED.label,
                status      = EXCLUDED.status,
                is_active   = EXCLUDED.is_active
        """)
    )

    # ── 3c. Vínculo device ↔ instalação ──────────────────────────────────────
    conn.execute(
        sa.text("""
            INSERT INTO device_installations (
                device_id, installation_id, valid_from, created_at
            )
            SELECT
                d.id,
                i.id,
                now(),
                now()
            FROM devices d
            JOIN installations i ON i.slug = 'escola'
            WHERE d.imei = 'sm3egw-iemedidor'
              AND NOT EXISTS (
                  SELECT 1 FROM device_installations di
                  WHERE di.device_id = d.id
                    AND di.installation_id = i.id
                    AND di.valid_to IS NULL
              )
        """)
    )


def downgrade() -> None:
    if _slug() == _TARGET_SLUG:
        conn = op.get_bind()
        # Remove vínculo
        conn.execute(
            sa.text("""
                DELETE FROM device_installations
                WHERE device_id = (SELECT id FROM devices WHERE imei = 'sm3egw-iemedidor')
                  AND installation_id = (SELECT id FROM installations WHERE slug = 'escola')
            """)
        )
        # Remove device (só se não houver leituras)
        conn.execute(
            sa.text("""
                DELETE FROM devices
                WHERE imei = 'sm3egw-iemedidor'
                  AND NOT EXISTS (
                      SELECT 1 FROM device_installations di
                      WHERE di.device_id = devices.id
                  )
            """)
        )
        # Remove instalação
        conn.execute(
            sa.text("""
                DELETE FROM installations
                WHERE slug = 'escola'
                  AND NOT EXISTS (
                      SELECT 1 FROM device_installations di
                      JOIN installations i ON i.id = di.installation_id
                      WHERE i.slug = 'escola'
                  )
            """)
        )

    op.drop_column("installations", "kind")
