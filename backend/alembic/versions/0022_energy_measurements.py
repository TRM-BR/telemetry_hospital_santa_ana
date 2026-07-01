"""Create energy_measurements hypertable (SM-3EGW, Escola).

Tabela de dados limpos de energia — papel análogo ao parsed_measurements
do sistema hidráulico. Espelha o padrão hypertable do 0001_initial_schema.py:
  - PK composta (id, collected_at_utc) — exigência do TimescaleDB
  - chunk_time_interval = 7 dias
  - Índices (device_id, ts) e (installation_id, ts)
  - Dedup UNIQUE (device_id, collected_at_utc)

Colunas de métrica:
  - Instantâneos (float):    pt, qt, uarms, ubrms, ucrms, itrms, pft
  - Acumulados (NUMERIC):    ept_c, ept_g, eqt_g  — monotônicos, precisão fixa
  - Deltas (NUMERIC):        delta_ept_c, delta_ept_g — para o gráfico de barras
  - Diagnóstico (int):       rssi_gsm (-999 já mapeado para NULL pelo parser)

collected_at_utc = received_at_utc (horário de chegada na bridge, gerado no app).
O payload SM-3EGW não traz timestamp próprio.

Revision ID: 0022
Revises: 0021
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "energy_measurements",
        # PK composta — TimescaleDB exige coluna de partição na PK
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("collected_at_utc", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("raw_message_id", sa.BigInteger(), nullable=True),
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=True),
        # ── Instantâneos / fase ────────────────────────────────────────────────
        sa.Column("active_power_total_w", sa.Float(), nullable=True),        # pt
        sa.Column("reactive_power_total_var", sa.Float(), nullable=True),    # qt
        sa.Column("voltage_phase_a_v", sa.Float(), nullable=True),           # uarms
        sa.Column("voltage_phase_b_v", sa.Float(), nullable=True),           # ubrms
        sa.Column("voltage_phase_c_v", sa.Float(), nullable=True),           # ucrms
        sa.Column("current_total_a", sa.Float(), nullable=True),             # itrms
        sa.Column("power_factor_total", sa.Float(), nullable=True),          # pft
        # ── Acumulados monotônicos — NUMERIC(18,3) para não perder precisão ───
        sa.Column("active_energy_consumed_total_kwh", sa.Numeric(18, 3), nullable=True),      # ept_c
        sa.Column("active_energy_generated_total_kwh", sa.Numeric(18, 3), nullable=True),     # ept_g
        sa.Column("reactive_energy_generated_total_kvarh", sa.Numeric(18, 3), nullable=True), # eqt_g
        # ── Deltas por telemetria — NUMERIC(18,3) ─────────────────────────────
        sa.Column("delta_active_energy_consumed_kwh", sa.Numeric(18, 3), nullable=True),      # deltaeptc
        sa.Column("delta_active_energy_generated_kwh", sa.Numeric(18, 3), nullable=True),     # deltaeptg
        # ── Diagnóstico ───────────────────────────────────────────────────────
        sa.Column("gsm_signal_rssi_dbm", sa.Integer(), nullable=True),       # rssi_gsm
        # ── Auditoria ─────────────────────────────────────────────────────────
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", "collected_at_utc"),
    )

    # Converte em hypertable (TimescaleDB)
    op.execute(
        """
        SELECT create_hypertable(
            'energy_measurements',
            'collected_at_utc',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        );
        """
    )

    # Dedup: um device não pode ter duas leituras no mesmo instante
    op.execute(
        """
        CREATE UNIQUE INDEX uq_energy_device_ts
        ON energy_measurements (device_id, collected_at_utc);
        """
    )

    # Índices de query (séries por device e por instalação)
    op.execute(
        "CREATE INDEX ix_energy_device_id ON energy_measurements (device_id, collected_at_utc DESC);"
    )
    op.execute(
        "CREATE INDEX ix_energy_installation_id ON energy_measurements (installation_id, collected_at_utc DESC);"
    )


def downgrade() -> None:
    op.drop_table("energy_measurements")
