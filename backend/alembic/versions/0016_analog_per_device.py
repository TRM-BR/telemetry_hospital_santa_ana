"""Schema analógico per-device — Hospital Santa Ana (DTN-200-FPS0).

Mudanças:
  parsed_measurements:
    - ADD COLUMN current_ma DOUBLE PRECISION NULL
    - ADD COLUMN voltage_v  DOUBLE PRECISION NULL
    - DROP UNIQUE (device_id, collected_at_utc, hist_index) se existir
    - ADD UNIQUE (device_id, collected_at_utc)  [dedup correto para analógico]

  devices:
    - ADD COLUMN status VARCHAR(32) NULL DEFAULT 'auto_detected'
    - ADD COLUMN label  VARCHAR(128) NULL

  device_installations:
    - ADD UNIQUE (device_id, installation_id) WHERE valid_to IS NULL

  alert_state:
    - ADD COLUMN device_id BIGINT NULL
    - DROP UNIQUE (installation_id, rule_key) se existir
    - ADD UNIQUE (installation_id, device_id, rule_key) WHERE device_id IS NOT NULL
    - ADD UNIQUE (installation_id, rule_key) WHERE device_id IS NULL

  alert_events:
    - ADD COLUMN device_id BIGINT NULL

Revision ID: 0016
Revises: 0015
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── parsed_measurements: colunas analógicas ──────────────────────────────
    op.add_column(
        "parsed_measurements",
        sa.Column("current_ma", sa.Double(), nullable=True),
    )
    op.add_column(
        "parsed_measurements",
        sa.Column("voltage_v", sa.Double(), nullable=True),
    )

    # Dedup analógico: remove index antigo e cria novo sem hist_index.
    # O index antigo pode ter nome diferente dependendo da migration inicial.
    # Tratamos como best-effort (IF EXISTS via DDL direto).
    op.execute("""
        DROP INDEX IF EXISTS uq_parsed_measurements_device_ts_hist;
        DROP INDEX IF EXISTS ix_parsed_measurements_device_ts_hist;
    """)
    # Cria UNIQUE sem hist_index — header e slots do mesmo segundo tornam-se um só.
    op.create_unique_constraint(
        "uq_parsed_device_collected_at",
        "parsed_measurements",
        ["device_id", "collected_at_utc"],
    )

    # ── devices: campos de autodetecção ─────────────────────────────────────
    op.add_column(
        "devices",
        sa.Column("status", sa.String(32), nullable=True, server_default="auto_detected"),
    )
    op.add_column(
        "devices",
        sa.Column("label", sa.String(128), nullable=True),
    )

    # ── device_installations: UNIQUE ativo para evitar duplicar vínculo ─────
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
          uq_device_installations_active
          ON device_installations (device_id, installation_id)
          WHERE valid_to IS NULL;
    """)

    # ── alert_state: coluna device_id + índices parciais ────────────────────
    op.add_column(
        "alert_state",
        sa.Column("device_id", sa.BigInteger(), nullable=True),
    )
    # Remove constraint global antiga (installation_id, rule_key) — pode ter nome variado
    op.execute("""
        DO $$
        DECLARE c text;
        BEGIN
            SELECT constraint_name INTO c
            FROM information_schema.table_constraints
            WHERE table_name = 'alert_state'
              AND constraint_type = 'UNIQUE'
              AND constraint_name NOT LIKE '%device%';
            IF c IS NOT NULL THEN
                EXECUTE 'ALTER TABLE alert_state DROP CONSTRAINT ' || quote_ident(c);
            END IF;
        END;
        $$;
    """)
    # Índices parciais corretos
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
          uq_alert_state_per_device
          ON alert_state (installation_id, device_id, rule_key)
          WHERE device_id IS NOT NULL;
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
          uq_alert_state_no_device
          ON alert_state (installation_id, rule_key)
          WHERE device_id IS NULL;
    """)

    # ── alert_events: coluna device_id ───────────────────────────────────────
    op.add_column(
        "alert_events",
        sa.Column("device_id", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alert_events", "device_id")

    op.execute("DROP INDEX IF EXISTS uq_alert_state_per_device;")
    op.execute("DROP INDEX IF EXISTS uq_alert_state_no_device;")
    op.drop_column("alert_state", "device_id")

    op.execute("DROP INDEX IF EXISTS uq_device_installations_active;")

    op.drop_column("devices", "label")
    op.drop_column("devices", "status")

    op.drop_constraint("uq_parsed_device_collected_at", "parsed_measurements", type_="unique")
    op.drop_column("parsed_measurements", "voltage_v")
    op.drop_column("parsed_measurements", "current_ma")
