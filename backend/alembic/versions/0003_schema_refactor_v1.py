"""Schema refactor V1 — alinha ao modelo definitivo.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-21

ATENÇÃO: migration destrutiva.
Execute APENAS no banco telemetry_barueri. NUNCA no hydroforce_db legado.
Faça backup/snapshot antes.

Mudanças:
  1. installations       → remove colunas legadas (address, lat, lng,
                           has_reservoir, reservoir_volume_m3)
  2. device_installations → renomeia started_at→valid_from, ended_at→valid_to;
                            recria índice único de vínculo ativo
  3. calibrations        → remove colunas antigas; adiciona colunas do legado
                           (ref_min_mca, ref_max_mca, n_low, n_high,
                            window_days, last_source_ts, calc_version);
                           UNIQUE em device_id
  4. derived_metrics     → DROP + RECREATE como tabela estreita
                           (metric_name + value + unit)
  5. alert_rules         → renomeia metric→metric_name; remove requires_reservoir;
                           deleta regras antigas (serão reseed em 0004)
  6. alert_state / alert_events → TRUNCATE (regenerados pelo alert_worker)
  7. parsed_measurements → reset derive_status='pending' para forçar rederivação
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─────────────────────────────────────────────────────────────────────────
    # 1. installations — remove colunas não usadas na V1
    # ─────────────────────────────────────────────────────────────────────────
    op.drop_column("installations", "address")
    op.drop_column("installations", "lat")
    op.drop_column("installations", "lng")
    op.drop_column("installations", "has_reservoir")
    op.drop_column("installations", "reservoir_volume_m3")

    # ─────────────────────────────────────────────────────────────────────────
    # 2. device_installations — renomeia colunas; recria índice de vínculo ativo
    # ─────────────────────────────────────────────────────────────────────────
    op.execute(
        "DROP INDEX IF EXISTS idx_device_installation_active;"
    )
    op.alter_column("device_installations", "started_at",
                    new_column_name="valid_from")
    op.alter_column("device_installations", "ended_at",
                    new_column_name="valid_to")
    op.execute("""
        CREATE UNIQUE INDEX idx_device_installation_active
        ON device_installations (device_id)
        WHERE valid_to IS NULL;
    """)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. calibrations — substitui colunas de kPa por MCA + metadados de cálculo
    # ─────────────────────────────────────────────────────────────────────────
    op.execute("DROP INDEX IF EXISTS idx_calibration_device_effective;")
    op.drop_column("calibrations", "effective_at")
    op.drop_column("calibrations", "pressure_offset_kpa")
    op.drop_column("calibrations", "pressure_scale")
    op.drop_column("calibrations", "pressure_ref_zero_kpa")
    op.drop_column("calibrations", "pressure_ref_full_kpa")
    op.drop_column("calibrations", "flow_liter_per_pulse")

    op.add_column("calibrations", sa.Column("ref_min_mca",     sa.Float(),   nullable=True))
    op.add_column("calibrations", sa.Column("ref_max_mca",     sa.Float(),   nullable=True))
    op.add_column("calibrations", sa.Column("n_low",           sa.Integer(), nullable=True))
    op.add_column("calibrations", sa.Column("n_high",          sa.Integer(), nullable=True))
    op.add_column("calibrations", sa.Column("window_days",     sa.Integer(), nullable=True))
    op.add_column("calibrations", sa.Column(
        "last_source_ts", sa.TIMESTAMP(timezone=True), nullable=True
    ))
    op.add_column("calibrations", sa.Column(
        "calc_version", sa.String(32), nullable=False, server_default="'v1'"
    ))
    op.add_column("calibrations", sa.Column(
        "updated_at", sa.TIMESTAMP(timezone=True), nullable=True
    ))

    # Um dispositivo tem no máximo uma linha de calibração (rewrite on update)
    op.execute("""
        CREATE UNIQUE INDEX uq_calibration_device
        ON calibrations (device_id);
    """)

    # ─────────────────────────────────────────────────────────────────────────
    # 4. derived_metrics — DROP + RECREATE como tabela estreita
    #    (metric_name + value + unit por leitura)
    #
    #    Métricas armazenadas pelo derive_worker:
    #      pressure     (mca)   — sensor 1
    #      pressure2    (mca)   — sensor 2
    #      level_pct    (%)
    #      level_mca    (mca)
    #      level_m      (m)
    #      flow1_lph    (lph)
    #      flow2_lph    (lph)
    #      flow_total_lph (lph) — flow1+flow2 (usado diretamente pelas regras)
    #      flow1_m3h    (m3h)
    #      flow2_m3h    (m3h)
    #      flow_total_m3h (m3h) — para cálculo de ratio 24h/30d
    #      temperature  (°C)
    #      battery_v    (V)
    # ─────────────────────────────────────────────────────────────────────────
    op.execute("DROP TABLE IF EXISTS derived_metrics CASCADE;")

    op.execute("""
        CREATE TABLE derived_metrics (
            id                   BIGSERIAL        NOT NULL,
            derived_at_utc       TIMESTAMPTZ      NOT NULL,
            parsed_measurement_id BIGINT,
            device_id            BIGINT           NOT NULL,
            installation_id      BIGINT,
            metric_name          VARCHAR(32)      NOT NULL,
            value                FLOAT,
            unit                 VARCHAR(16),
            created_at           TIMESTAMPTZ      NOT NULL DEFAULT now(),
            PRIMARY KEY (id, derived_at_utc)
        );
    """)

    op.execute("""
        SELECT create_hypertable(
            'derived_metrics',
            'derived_at_utc',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        );
    """)

    # Dedup: um único valor por (dispositivo, instante, métrica)
    op.execute("""
        CREATE UNIQUE INDEX uq_derived_device_ts_metric
        ON derived_metrics (device_id, derived_at_utc, metric_name);
    """)

    op.execute("""
        CREATE INDEX idx_derived_installation_time
        ON derived_metrics (installation_id, derived_at_utc DESC);
    """)

    op.execute("""
        CREATE INDEX idx_derived_device_time
        ON derived_metrics (device_id, derived_at_utc DESC);
    """)

    # Índice para a query de séries por instalação + métrica (usada pela API)
    op.execute("""
        CREATE INDEX idx_derived_inst_metric_time
        ON derived_metrics (installation_id, metric_name, derived_at_utc DESC);
    """)

    # ─────────────────────────────────────────────────────────────────────────
    # 5. alert_rules — renomeia coluna; remove requires_reservoir;
    #    apaga regras antigas (serão re-inseridas com métrica correta em 0004)
    # ─────────────────────────────────────────────────────────────────────────
    op.alter_column("alert_rules", "metric", new_column_name="metric_name")
    op.drop_column("alert_rules", "requires_reservoir")

    # Apaga regras globais (installation_id IS NULL); as por instalação ficam
    op.execute("DELETE FROM alert_rules WHERE installation_id IS NULL;")

    # ─────────────────────────────────────────────────────────────────────────
    # 6. alert_state / alert_events — limpa estado antigo
    # ─────────────────────────────────────────────────────────────────────────
    op.execute("TRUNCATE TABLE alert_state;")
    op.execute("TRUNCATE TABLE alert_events;")

    # ─────────────────────────────────────────────────────────────────────────
    # 7. parsed_measurements — reset para forçar rederivação no novo schema
    # ─────────────────────────────────────────────────────────────────────────
    op.execute("""
        UPDATE parsed_measurements
        SET derive_status    = 'pending',
            derive_attempts  = 0,
            last_attempt_at  = NULL,
            processing_since = NULL,
            worker_id        = NULL,
            error_message    = NULL;
    """)

    # ─────────────────────────────────────────────────────────────────────────
    # 8. auth_logs — FK para users (ON DELETE SET NULL)
    # ─────────────────────────────────────────────────────────────────────────
    op.create_foreign_key(
        "fk_auth_logs_user_id", "auth_logs", "users",
        ["user_id"], ["id"], ondelete="SET NULL",
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 9. CHECK constraints — equivalentes aos ENUMs do legado
    # ─────────────────────────────────────────────────────────────────────────
    op.execute("""
        ALTER TABLE users
        ADD CONSTRAINT ck_users_role
        CHECK (role IN ('admin', 'operador', 'viewer'));
    """)
    op.execute("""
        ALTER TABLE auth_logs
        ADD CONSTRAINT ck_auth_logs_action
        CHECK (action IN ('login_ok', 'login_fail', 'logout'));
    """)


def downgrade() -> None:
    """
    Downgrade parcial — restaura colunas removidas com valores NULL.
    Derived_metrics NÃO é restaurada (dados perdidos irrecuperavelmente sem backup).
    """
    # 9. CHECK constraints
    op.execute("ALTER TABLE auth_logs DROP CONSTRAINT IF EXISTS ck_auth_logs_action;")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role;")

    # 8. auth_logs FK
    op.drop_constraint("fk_auth_logs_user_id", "auth_logs", type_="foreignkey")

    # 7. parsed_measurements — não há o que desfazer (derive_status fica pending)

    # 5. alert_rules — restaura coluna removida
    op.add_column("alert_rules", sa.Column(
        "requires_reservoir", sa.Boolean(),
        nullable=False, server_default="false"
    ))
    op.alter_column("alert_rules", "metric_name", new_column_name="metric")

    # 3. calibrations — restaura colunas antigas
    op.execute("DROP INDEX IF EXISTS uq_calibration_device;")
    op.drop_column("calibrations", "updated_at")
    op.drop_column("calibrations", "calc_version")
    op.drop_column("calibrations", "last_source_ts")
    op.drop_column("calibrations", "window_days")
    op.drop_column("calibrations", "n_high")
    op.drop_column("calibrations", "n_low")
    op.drop_column("calibrations", "ref_max_mca")
    op.drop_column("calibrations", "ref_min_mca")
    op.add_column("calibrations", sa.Column(
        "flow_liter_per_pulse", sa.Float(),
        nullable=False, server_default="1"
    ))
    op.add_column("calibrations", sa.Column(
        "pressure_ref_full_kpa", sa.Float(), nullable=True
    ))
    op.add_column("calibrations", sa.Column(
        "pressure_ref_zero_kpa", sa.Float(), nullable=True
    ))
    op.add_column("calibrations", sa.Column(
        "pressure_scale", sa.Float(),
        nullable=False, server_default="1"
    ))
    op.add_column("calibrations", sa.Column(
        "pressure_offset_kpa", sa.Float(),
        nullable=False, server_default="0"
    ))
    op.add_column("calibrations", sa.Column(
        "effective_at", sa.TIMESTAMP(timezone=True), nullable=True
    ))
    op.execute("""
        CREATE INDEX idx_calibration_device_effective
        ON calibrations (device_id, effective_at);
    """)

    # 2. device_installations — desfaz renomeação
    op.execute("DROP INDEX IF EXISTS idx_device_installation_active;")
    op.alter_column("device_installations", "valid_from",
                    new_column_name="started_at")
    op.alter_column("device_installations", "valid_to",
                    new_column_name="ended_at")
    op.execute("""
        CREATE UNIQUE INDEX idx_device_installation_active
        ON device_installations (device_id)
        WHERE ended_at IS NULL;
    """)

    # 1. installations — restaura colunas com NULL
    op.add_column("installations", sa.Column(
        "reservoir_volume_m3", sa.Float(), nullable=True
    ))
    op.add_column("installations", sa.Column(
        "has_reservoir", sa.Boolean(),
        nullable=False, server_default="true"
    ))
    op.add_column("installations", sa.Column("lng",     sa.Double(), nullable=True))
    op.add_column("installations", sa.Column("lat",     sa.Double(), nullable=True))
    op.add_column("installations", sa.Column("address", sa.String(512), nullable=True))
