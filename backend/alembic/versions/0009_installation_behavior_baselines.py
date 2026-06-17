"""0009_installation_behavior_baselines — Baseline comportamental por instalação.

Cria a tabela installation_behavior_baselines, que armazena o perfil estatístico
de cada canal de cada instalação segmentado por período (janela móvel de 30 dias
fechados, recalculada diariamente pelo behavior_baseline_worker).

Tipos numéricos seguem o schema real:
  - id e installation_id são BigInteger (installations.id é BIGINT — 0001).

Campos de cobertura da janela:
  - window_days  : duração da janela (default 30; guardado por linha para
                   auditar mudanças futuras).
  - expected_samples : nº teórico de leituras na janela (ex.: 30d × 96/d = 2880).
                       Comparar com sample_count distingue "baixa amostragem"
                       de "instalação nova" sem depender só de coverage_pct.

Substitui a 0009 anterior (0009_adaptive_alert_schema) que nunca foi aplicada em
produção e criava tabelas/colunas incompatíveis com o estado real do banco (0008).

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "installation_behavior_baselines",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        # Canal hidráulico: 'street_inlet', 'tank_outlet'
        sa.Column("channel_role", sa.String(30), nullable=False),
        # Métrica: 'flow1_lph', 'flow2_lph', etc.
        sa.Column("metric_name", sa.String(64), nullable=False),
        # Período: 'overall', 'night', 'day', 'business_hours', 'off_hours', 'weekend'
        sa.Column("period_type", sa.String(20), nullable=False),
        # ── Estatísticas descritivas ─────────────────────────────────────────
        sa.Column("mean", sa.Float(), nullable=False),
        sa.Column("std", sa.Float(), nullable=False),
        sa.Column("min", sa.Float(), nullable=True),
        sa.Column("max", sa.Float(), nullable=True),
        sa.Column("p05", sa.Float(), nullable=True),
        sa.Column("p10", sa.Float(), nullable=True),
        sa.Column("p25", sa.Float(), nullable=True),
        sa.Column("p50", sa.Float(), nullable=True),
        sa.Column("p75", sa.Float(), nullable=True),
        sa.Column("p90", sa.Float(), nullable=True),
        sa.Column("p95", sa.Float(), nullable=True),
        # ── Padrões de repouso e fluxo contínuo ──────────────────────────────
        sa.Column("zero_ratio", sa.Float(), nullable=False, server_default="0"),
        sa.Column("near_zero_ratio", sa.Float(), nullable=False, server_default="0"),
        sa.Column("longest_zero_minutes", sa.Float(), nullable=True),
        sa.Column("typical_zero_minutes", sa.Float(), nullable=True),
        sa.Column("longest_continuous_flow_minutes", sa.Float(), nullable=True),
        sa.Column("typical_continuous_flow_minutes", sa.Float(), nullable=True),
        sa.Column("minimum_night_flow", sa.Float(), nullable=True),
        # ── Limites comportamentais inferidos ─────────────────────────────────
        sa.Column("normal_low", sa.Float(), nullable=True),
        sa.Column("normal_high", sa.Float(), nullable=True),
        sa.Column("anomaly_low", sa.Float(), nullable=True),
        sa.Column("anomaly_high", sa.Float(), nullable=True),
        sa.Column("typical_variation_per_hour", sa.Float(), nullable=True),
        # ── Classificação ─────────────────────────────────────────────────────
        sa.Column("profile_type", sa.String(30), nullable=True),
        # 'low' | 'medium' | 'high' | 'consolidated'
        sa.Column("confidence", sa.String(15), nullable=False),
        # ── Cobertura e janela de cálculo ─────────────────────────────────────
        sa.Column("coverage_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("window_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("expected_samples", sa.Integer(), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("window_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["installations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_inst_behavior_baseline_slot",
        "installation_behavior_baselines",
        ["installation_id", "channel_role", "metric_name", "period_type"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_inst_behavior_baseline_slot",
                  table_name="installation_behavior_baselines")
    op.drop_table("installation_behavior_baselines")
