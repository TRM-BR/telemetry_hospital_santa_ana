"""Initial schema — todas as tabelas da V1.

Revision ID: 0001
Revises: (none)
Create Date: 2026-05-20

Inclui:
  - Extensão TimescaleDB
  - Todas as tabelas (ordem respeita FKs)
  - Hypertables: parsed_measurements, derived_metrics
  - Índices parciais para as filas de workers
  - Índices de performance para as consultas do dashboard/API
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── TimescaleDB ──────────────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")

    # ── installations ────────────────────────────────────────────────────────
    op.create_table(
        "installations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(64), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.String(512), nullable=True),
        sa.Column("lat", sa.Double(), nullable=True),
        sa.Column("lng", sa.Double(), nullable=True),
        sa.Column("has_reservoir", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("reservoir_volume_m3", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_installations_slug", "installations", ["slug"], unique=True)

    # ── devices ──────────────────────────────────────────────────────────────
    op.create_table(
        "devices",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("imei", sa.String(32), unique=True, nullable=False),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("firmware_version", sa.String(32), nullable=True),
        sa.Column("serial_number", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_devices_imei", "devices", ["imei"], unique=True)

    # ── device_installations ─────────────────────────────────────────────────
    op.create_table(
        "device_installations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "device_id",
            sa.BigInteger(),
            sa.ForeignKey("devices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "installation_id",
            sa.BigInteger(),
            sa.ForeignKey("installations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("ended_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_di_device_id", "device_installations", ["device_id"])
    op.create_index("ix_di_installation_id", "device_installations", ["installation_id"])
    # Um dispositivo só pode ter um vínculo ativo por vez
    op.execute(
        """
        CREATE UNIQUE INDEX idx_device_installation_active
        ON device_installations (device_id)
        WHERE ended_at IS NULL;
        """
    )

    # ── calibrations ─────────────────────────────────────────────────────────
    op.create_table(
        "calibrations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "device_id",
            sa.BigInteger(),
            sa.ForeignKey("devices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("effective_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("pressure_offset_kpa", sa.Float(), nullable=False, server_default="0"),
        sa.Column("pressure_scale", sa.Float(), nullable=False, server_default="1"),
        sa.Column("pressure_ref_zero_kpa", sa.Float(), nullable=True),
        sa.Column("pressure_ref_full_kpa", sa.Float(), nullable=True),
        sa.Column("flow_liter_per_pulse", sa.Float(), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_calibration_device_effective", "calibrations", ["device_id", "effective_at"])

    # ── raw_messages ─────────────────────────────────────────────────────────
    op.create_table(
        "raw_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "received_at_utc",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("topic", sa.String(255), nullable=False),
        sa.Column("imei", sa.String(32), nullable=True),
        sa.Column("payload_raw", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("parse_status", sa.String(20), nullable=False, server_default="'pending'"),
        sa.Column("parse_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("processing_since", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("worker_id", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_raw_received_at_utc", "raw_messages", ["received_at_utc"])
    op.create_index("ix_raw_imei", "raw_messages", ["imei"])
    # Dedup: mesmo payload não entra duas vezes
    op.create_index(
        "uq_raw_origin_topic_hash",
        "raw_messages",
        ["origin", "topic", "payload_hash"],
        unique=True,
    )
    # Índice parcial para a fila do parse_worker (CRÍTICO para performance)
    op.execute(
        """
        CREATE INDEX idx_raw_parse_queue
        ON raw_messages (parse_status, last_attempt_at)
        WHERE parse_status IN ('pending', 'temporary_error');
        """
    )

    # ── parsed_measurements (HYPERTABLE) ─────────────────────────────────────
    op.create_table(
        "parsed_measurements",
        # PK composta — TimescaleDB exige coluna de partição na PK
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("collected_at_utc", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("raw_message_id", sa.BigInteger(), nullable=True),
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=True),
        sa.Column("hist_index", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("temperature2", sa.Float(), nullable=True),
        sa.Column("pressure_raw", sa.Float(), nullable=True),
        sa.Column("pressure2_raw", sa.Float(), nullable=True),
        sa.Column("count_pulses", sa.Float(), nullable=True),
        sa.Column("count2_pulses", sa.Float(), nullable=True),
        sa.Column("signal_rssi", sa.Integer(), nullable=True),
        sa.Column("battery_v", sa.Float(), nullable=True),
        sa.Column("derive_status", sa.String(20), nullable=False, server_default="'pending'"),
        sa.Column("derive_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("processing_since", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("worker_id", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", "collected_at_utc"),
    )
    # Transforma em hypertable (particiona por tempo)
    op.execute(
        """
        SELECT create_hypertable(
            'parsed_measurements',
            'collected_at_utc',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        );
        """
    )
    # Dedup
    op.execute(
        """
        CREATE UNIQUE INDEX uq_parsed_device_ts_hist
        ON parsed_measurements (device_id, collected_at_utc, hist_index);
        """
    )
    # Índice parcial para a fila do derive_worker
    op.execute(
        """
        CREATE INDEX idx_parsed_derive_queue
        ON parsed_measurements (derive_status, last_attempt_at)
        WHERE derive_status IN ('pending', 'temporary_error');
        """
    )
    op.execute(
        "CREATE INDEX ix_parsed_device_id ON parsed_measurements (device_id);"
    )
    op.execute(
        "CREATE INDEX ix_parsed_installation_id ON parsed_measurements (installation_id);"
    )

    # ── derived_metrics (HYPERTABLE) ─────────────────────────────────────────
    op.create_table(
        "derived_metrics",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("derived_at_utc", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("parsed_measurement_id", sa.BigInteger(), nullable=True),
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=True),
        sa.Column("level_pct", sa.Float(), nullable=True),
        sa.Column("pressure1_mca", sa.Float(), nullable=True),
        sa.Column("pressure2_mca", sa.Float(), nullable=True),
        sa.Column("flow1_lph", sa.Float(), nullable=True),
        sa.Column("flow2_lph", sa.Float(), nullable=True),
        sa.Column("flow1_m3h", sa.Float(), nullable=True),
        sa.Column("flow2_m3h", sa.Float(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("battery_v", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", "derived_at_utc"),
    )
    op.execute(
        """
        SELECT create_hypertable(
            'derived_metrics',
            'derived_at_utc',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        );
        """
    )
    op.execute(
        "CREATE INDEX idx_derived_installation_time ON derived_metrics (installation_id, derived_at_utc);"
    )
    op.execute(
        "CREATE INDEX idx_derived_device_time ON derived_metrics (device_id, derived_at_utc);"
    )

    # ── alert_rules ──────────────────────────────────────────────────────────
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "installation_id",
            sa.BigInteger(),
            sa.ForeignKey("installations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("rule_key", sa.String(64), nullable=False),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("operator", sa.String(4), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("alert_type", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("message_template", sa.String(512), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("requires_reservoir", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("window_minutes", sa.SmallInteger(), nullable=True),
        sa.Column("hysteresis_minutes", sa.SmallInteger(), nullable=False, server_default="5"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_alert_rule_scope
        ON alert_rules (COALESCE(installation_id, -1), rule_key);
        """
    )

    # ── alert_state ──────────────────────────────────────────────────────────
    op.create_table(
        "alert_state",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "installation_id",
            sa.BigInteger(),
            sa.ForeignKey("installations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rule_key", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("first_triggered_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_triggered_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("current_value", sa.Float(), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "uq_alert_state_installation_rule",
        "alert_state",
        ["installation_id", "rule_key"],
        unique=True,
    )
    op.execute(
        """
        CREATE INDEX idx_alert_state_active
        ON alert_state (installation_id)
        WHERE is_active = true;
        """
    )

    # ── alert_events ─────────────────────────────────────────────────────────
    op.create_table(
        "alert_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "installation_id",
            sa.BigInteger(),
            sa.ForeignKey("installations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rule_key", sa.String(64), nullable=False),
        sa.Column("alert_type", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="'ativo'"),
        sa.Column("current_value", sa.Float(), nullable=True),
        sa.Column(
            "triggered_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_alert_event_installation_id", "alert_events", ["installation_id"])
    op.create_index("ix_alert_event_triggered_at", "alert_events", ["triggered_at"])
    op.execute(
        """
        CREATE INDEX idx_alert_event_active
        ON alert_events (installation_id)
        WHERE status = 'ativo';
        """
    )

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(64), unique=True, nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=True),
        sa.Column("hashed_password", sa.String(128), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="'viewer'"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    # ── auth_logs ─────────────────────────────────────────────────────────────
    op.create_table(
        "auth_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("username_attempted", sa.String(64), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_auth_log_user_id", "auth_logs", ["user_id"])
    op.create_index("ix_auth_log_occurred_at", "auth_logs", ["occurred_at"])

    # ── notices ───────────────────────────────────────────────────────────────
    op.create_table(
        "notices",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_notices_expires_at", "notices", ["expires_at"])


def downgrade() -> None:
    """Remove todas as tabelas na ordem inversa (respeitando FKs)."""
    op.drop_table("notices")
    op.drop_table("auth_logs")
    op.drop_table("users")
    op.drop_table("alert_events")
    op.drop_table("alert_state")
    op.drop_table("alert_rules")
    op.drop_table("derived_metrics")
    op.drop_table("parsed_measurements")
    op.drop_table("raw_messages")
    op.drop_table("calibrations")
    op.drop_table("device_installations")
    op.drop_table("devices")
    op.drop_table("installations")
    op.execute("DROP EXTENSION IF EXISTS timescaledb;")
