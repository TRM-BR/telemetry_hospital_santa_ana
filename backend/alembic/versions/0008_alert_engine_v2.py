"""0008_alert_engine_v2 — Motor de alertas v2 (detectores, baselines, schedules).

Mudanças:
  • CRIA metric_baselines     — média/std de cada métrica por instalação (30d)
  • CRIA installation_schedules — horários de operação derivados de consumo (14d)
  • CRIA alert_views            — rastreio de "visto" por usuário
  • ADD colunas ricas em alert_state (alert_type, severity, titulo, etc.)
  • ADD colunas ricas em alert_events (titulo, mensagem_usuario, etc.)
  • TRUNCA alert_state e alert_events (dados incompatíveis com o novo motor)
  • DROP alert_rules              — substituída pelo motor de detectores

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # ── 1. metric_baselines ──────────────────────────────────────────────────
    op.create_table(
        "metric_baselines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("installation_id", sa.Integer(), nullable=False),
        sa.Column("metric_name", sa.String(64), nullable=False),
        sa.Column("mean", sa.Float(), nullable=False),
        sa.Column("std", sa.Float(), nullable=False),
        sa.Column("p10", sa.Float(), nullable=True),
        sa.Column("p90", sa.Float(), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("window_days", sa.SmallInteger(), nullable=False, server_default="30"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_metric_baselines_inst_metric",
        "metric_baselines",
        ["installation_id", "metric_name"],
        unique=True,
    )

    # ── 2. installation_schedules ────────────────────────────────────────────
    # dow: 0=domingo … 6=sábado (ISO: 0=domingo)
    # Cada linha representa um (installation, dia-da-semana, hora) com o
    # consumo esperado. baseline_worker popula; alert_worker consulta.
    op.create_table(
        "installation_schedules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("installation_id", sa.Integer(), nullable=False),
        sa.Column("dow", sa.SmallInteger(), nullable=False),   # 0–6
        sa.Column("hour", sa.SmallInteger(), nullable=False),  # 0–23
        sa.Column("mean_flow_lph", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_active_hour", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_installation_schedules_slot",
        "installation_schedules",
        ["installation_id", "dow", "hour"],
        unique=True,
    )
    op.create_index(
        "idx_installation_schedules_active",
        "installation_schedules",
        ["installation_id"],
        postgresql_where=sa.text("is_active_hour = true"),
    )

    # ── 3. alert_views ───────────────────────────────────────────────────────
    op.create_table(
        "alert_views",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("installation_id", sa.Integer(), nullable=False),
        sa.Column("rule_key", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_alert_views_user_alert",
        "alert_views",
        ["user_id", "installation_id", "rule_key"],
        unique=True,
    )

    # ── 4. Colunas ricas em alert_state ──────────────────────────────────────
    # TRUNCATE primeiro — dados antigos incompatíveis com o novo motor
    op.execute("TRUNCATE TABLE alert_state")

    op.add_column("alert_state",
        sa.Column("alert_type", sa.String(30), nullable=True))
    op.add_column("alert_state",
        sa.Column("severity", sa.String(10), nullable=True))
    op.add_column("alert_state",
        sa.Column("titulo", sa.String(200), nullable=True))
    op.add_column("alert_state",
        sa.Column("mensagem_usuario", sa.Text(), nullable=True))
    op.add_column("alert_state",
        sa.Column("recomendacao", sa.Text(), nullable=True))
    op.add_column("alert_state",
        sa.Column("dados_relevantes", postgresql.JSONB(), nullable=True))

    # ── 5. Colunas ricas em alert_events ─────────────────────────────────────
    op.execute("TRUNCATE TABLE alert_events")

    op.add_column("alert_events",
        sa.Column("titulo", sa.String(200), nullable=True))
    op.add_column("alert_events",
        sa.Column("mensagem_usuario", sa.Text(), nullable=True))
    op.add_column("alert_events",
        sa.Column("recomendacao", sa.Text(), nullable=True))
    op.add_column("alert_events",
        sa.Column("dados_relevantes", postgresql.JSONB(), nullable=True))

    # ── 6. DROP alert_rules ──────────────────────────────────────────────────
    op.drop_table("alert_rules")


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # Recria alert_rules (vazia — seeds precisam ser re-aplicados)
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("installation_id", sa.Integer(), nullable=True),
        sa.Column("rule_key", sa.String(64), nullable=False),
        sa.Column("metric_name", sa.String(64), nullable=False),
        sa.Column("operator", sa.String(4), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("alert_type", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("message_template", sa.String(512), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("window_minutes", sa.SmallInteger(), nullable=True),
        sa.Column("hysteresis_minutes", sa.SmallInteger(), nullable=False, server_default="5"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_alert_rule_scope", "alert_rules",
                    ["installation_id", "rule_key"], unique=True)

    # Remove colunas ricas
    for col in ("alert_type", "severity", "titulo", "mensagem_usuario",
                "recomendacao", "dados_relevantes"):
        op.drop_column("alert_state", col)
    for col in ("titulo", "mensagem_usuario", "recomendacao", "dados_relevantes"):
        op.drop_column("alert_events", col)

    op.drop_table("alert_views")
    op.drop_table("installation_schedules")
    op.drop_table("metric_baselines")
