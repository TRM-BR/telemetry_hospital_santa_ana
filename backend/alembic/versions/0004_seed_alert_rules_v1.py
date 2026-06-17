"""Seed das regras de alerta V1 (após refactor de schema).

Revision ID: 0004
Revises: 0003

Regras globais (installation_id=NULL) — aplicam-se a todas as instalações.
Diferenças em relação a 0002:
  - metric_name='pressure'        (era 'pressure1_mca')
  - rule_key 'pressao-1-baixa'    → 'pressao-baixa'
  - rule_key 'pressao-1-alta'     → 'pressao-alta'
  - Removidas: autonomia-critica, autonomia-atencao (sem reservoir_volume_m3 na V1)
  - Total: 11 regras (era 13)

Métricas referenciadas:
  level_pct        — direto de derived_metrics (metric_name='level_pct')
  pressure         — direto de derived_metrics (metric_name='pressure')
  flow_total_lph   — direto de derived_metrics (metric_name='flow_total_lph')
  data_age_minutes — calculado pelo alert_worker (não em derived_metrics)
  flow_ratio_24h_30d — calculado pelo alert_worker a partir de flow_total_m3h
"""
from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# (rule_key, metric_name, operator, threshold, alert_type, severity,
#  message_template, hysteresis_minutes)
_RULES_V1 = [
    # ── Nível do reservatório ────────────────────────────────────────────────
    (
        "nivel-critico", "level_pct", "<", 25.0,
        "consumo", "alta",
        "Reservatorio em nivel critico ({value:.1f}%).",
        10,
    ),
    (
        "nivel-atencao", "level_pct", "<", 60.0,
        "consumo", "media",
        "Reservatorio em atencao ({value:.1f}%).",
        10,
    ),
    # ── Pressão sensor 1 ─────────────────────────────────────────────────────
    (
        "pressao-baixa", "pressure", "<", 12.0,
        "pressao", "media",
        "Pressao baixa no sensor 1 ({value:.2f} MCA).",
        5,
    ),
    (
        "pressao-alta", "pressure", ">", 45.0,
        "pressao", "alta",
        "Pressao alta no sensor 1 ({value:.2f} MCA).",
        5,
    ),
    # ── Vazão ────────────────────────────────────────────────────────────────
    (
        "sem-fluxo", "flow_total_lph", "<=", 1.0,
        "sensor", "media",
        "Vazao sem fluxo no periodo atual ({value:.1f} L/h).",
        10,
    ),
    (
        "vazao-baixa", "flow_total_lph", "<", 120.0,
        "consumo", "baixa",
        "Vazao baixa ({value:.1f} L/h).",
        10,
    ),
    (
        "vazao-alta", "flow_total_lph", ">", 1500.0,
        "vazamento", "alta",
        "Vazao alta ({value:.1f} L/h).",
        5,
    ),
    # ── Atualização ──────────────────────────────────────────────────────────
    (
        "sem-atualizacao", "data_age_minutes", ">", 120.0,
        "sensor", "alta",
        "Sem atualizacao recente de telemetria ha {value:.0f} min.",
        5,
    ),
    # ── Consumo (razão 24h / 30d) ─────────────────────────────────────────────
    (
        "consumo-muito-alto", "flow_ratio_24h_30d", ">=", 1.7,
        "vazamento", "alta",
        "Possivel vazamento: consumo muito alto ({value:.2f}x da media).",
        15,
    ),
    (
        "consumo-acima", "flow_ratio_24h_30d", ">=", 1.3,
        "consumo", "media",
        "Consumo acima do padrao ({value:.2f}x da media).",
        15,
    ),
    (
        "consumo-abaixo", "flow_ratio_24h_30d", "<=", 0.4,
        "consumo", "baixa",
        "Consumo abaixo do esperado ({value:.2f}x da media).",
        15,
    ),
]


def upgrade() -> None:
    for row in _RULES_V1:
        (
            rule_key, metric_name, operator, threshold,
            alert_type, severity, message_template, hysteresis_minutes,
        ) = row
        op.execute(f"""
            INSERT INTO alert_rules
                (installation_id, rule_key, metric_name, operator, threshold,
                 alert_type, severity, message_template,
                 hysteresis_minutes, is_active)
            VALUES
                (NULL, '{rule_key}', '{metric_name}', '{operator}', {threshold},
                 '{alert_type}', '{severity}', '{message_template}',
                 {hysteresis_minutes}, true)
            ON CONFLICT DO NOTHING
        """)


def downgrade() -> None:
    keys = ", ".join(f"'{r[0]}'" for r in _RULES_V1)
    op.execute(f"""
        DELETE FROM alert_rules
        WHERE installation_id IS NULL
          AND rule_key IN ({keys})
    """)
