"""0007_fix_timestamptz — converte todas as colunas TIMESTAMP para TIMESTAMPTZ.

Contexto: asyncpg rejeita datetime tz-aware em colunas TIMESTAMP WITHOUT TIME
ZONE. A correção converte todas as colunas de timestamp para TIMESTAMPTZ, que
armazena internamente em UTC e retorna objetos Python timezone-aware.

Os dados já estavam em UTC — a conversão usa AT TIME ZONE 'UTC' para não
alterar os valores, só o tipo.

Para as colunas de partição das hypertables (collected_at_utc, derived_at_utc),
é necessário habilitar o parâmetro timescaledb.enable_unsafe_time_column_type_change.
Se o banco for vazio, a operação é imediata. Se houver dados, o TimescaleDB
2.6+ suporta a conversão com esse flag.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-21
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _alter(table: str, column: str) -> None:
    """ALTER COLUMN para TIMESTAMPTZ com USING ... AT TIME ZONE 'UTC'."""
    op.execute(
        f"ALTER TABLE {table} "
        f"ALTER COLUMN {column} TYPE TIMESTAMPTZ "
        f"USING {column} AT TIME ZONE 'UTC'"
    )


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # ── users ────────────────────────────────────────────────────────────────
    _alter("users", "created_at")
    _alter("users", "updated_at")
    _alter("users", "last_login_at")

    # ── auth_logs ────────────────────────────────────────────────────────────
    _alter("auth_logs", "occurred_at")

    # ── raw_messages ─────────────────────────────────────────────────────────
    _alter("raw_messages", "received_at_utc")
    _alter("raw_messages", "last_attempt_at")
    _alter("raw_messages", "processing_since")

    # ── parsed_measurements (hypertable) ─────────────────────────────────────
    # Colunas não-partição: ALTER normal
    _alter("parsed_measurements", "last_attempt_at")
    _alter("parsed_measurements", "processing_since")
    _alter("parsed_measurements", "created_at")
    # Coluna de partição: requer flag do TimescaleDB
    op.execute("SET timescaledb.enable_unsafe_time_column_type_change = 'on'")
    _alter("parsed_measurements", "collected_at_utc")
    op.execute("RESET timescaledb.enable_unsafe_time_column_type_change")

    # ── derived_metrics (hypertable) ─────────────────────────────────────────
    _alter("derived_metrics", "created_at")
    op.execute("SET timescaledb.enable_unsafe_time_column_type_change = 'on'")
    _alter("derived_metrics", "derived_at_utc")
    op.execute("RESET timescaledb.enable_unsafe_time_column_type_change")

    # ── alert_state ──────────────────────────────────────────────────────────
    _alter("alert_state", "first_triggered_at")
    _alter("alert_state", "last_triggered_at")
    _alter("alert_state", "last_resolved_at")
    _alter("alert_state", "updated_at")

    # ── alert_events ─────────────────────────────────────────────────────────
    _alter("alert_events", "triggered_at")
    _alter("alert_events", "resolved_at")

    # ── alert_rules ──────────────────────────────────────────────────────────
    _alter("alert_rules", "created_at")
    _alter("alert_rules", "updated_at")

    # ── installations ────────────────────────────────────────────────────────
    _alter("installations", "created_at")
    _alter("installations", "updated_at")

    # ── devices ──────────────────────────────────────────────────────────────
    _alter("devices", "created_at")
    _alter("devices", "updated_at")

    # ── device_installations ─────────────────────────────────────────────────
    _alter("device_installations", "valid_from")
    _alter("device_installations", "valid_to")
    _alter("device_installations", "created_at")

    # ── calibrations ─────────────────────────────────────────────────────────
    _alter("calibrations", "last_source_ts")
    _alter("calibrations", "created_at")
    _alter("calibrations", "updated_at")

    # ── notices ──────────────────────────────────────────────────────────────
    _alter("notices", "created_at")
    _alter("notices", "expires_at")


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # Reverte TIMESTAMPTZ → TIMESTAMP WITHOUT TIME ZONE.
    # Dados são preservados (AT TIME ZONE 'UTC' remove o offset sem mudar valor).

    def _revert(table: str, column: str) -> None:
        op.execute(
            f"ALTER TABLE {table} "
            f"ALTER COLUMN {column} TYPE TIMESTAMP WITHOUT TIME ZONE "
            f"USING {column} AT TIME ZONE 'UTC'"
        )

    _revert("users", "created_at")
    _revert("users", "updated_at")
    _revert("users", "last_login_at")
    _revert("auth_logs", "occurred_at")
    _revert("raw_messages", "received_at_utc")
    _revert("raw_messages", "last_attempt_at")
    _revert("raw_messages", "processing_since")
    _revert("parsed_measurements", "last_attempt_at")
    _revert("parsed_measurements", "processing_since")
    _revert("parsed_measurements", "created_at")
    op.execute("SET timescaledb.enable_unsafe_time_column_type_change = 'on'")
    _revert("parsed_measurements", "collected_at_utc")
    _revert("derived_metrics", "derived_at_utc")
    op.execute("RESET timescaledb.enable_unsafe_time_column_type_change")
    _revert("derived_metrics", "created_at")
    _revert("alert_state", "first_triggered_at")
    _revert("alert_state", "last_triggered_at")
    _revert("alert_state", "last_resolved_at")
    _revert("alert_state", "updated_at")
    _revert("alert_events", "triggered_at")
    _revert("alert_events", "resolved_at")
    _revert("alert_rules", "created_at")
    _revert("alert_rules", "updated_at")
    _revert("installations", "created_at")
    _revert("installations", "updated_at")
    _revert("devices", "created_at")
    _revert("devices", "updated_at")
    _revert("device_installations", "valid_from")
    _revert("device_installations", "valid_to")
    _revert("device_installations", "created_at")
    _revert("calibrations", "last_source_ts")
    _revert("calibrations", "created_at")
    _revert("calibrations", "updated_at")
    _revert("notices", "created_at")
    _revert("notices", "expires_at")
