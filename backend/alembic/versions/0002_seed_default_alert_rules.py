"""Seed das regras de alerta padrão (migradas do front legado alerts.ts).

Revision ID: 0002
Revises: 0001

Regras globais (installation_id=NULL) — aplicam-se a todas as instalações.
Limiares extraídos de react/src/services/alerts.ts:
  STATUS_CFG  → nivel, pressao, vazao, sem_atualizacao
  ANALYSIS_CFG → consumo (ratio 24h/30d), autonomia
"""
from __future__ import annotations

from alembic import op

# revision identifiers
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Regras: (rule_key, metric, operator, threshold, alert_type, severity,
#          message_template, requires_reservoir, hysteresis_minutes)
_DEFAULT_RULES = [
    # ── Nível do reservatório ────────────────────────────────────────────────
    (
        "nivel-critico", "level_pct", "<", 25.0,
        "consumo", "alta",
        "Reservatorio em nivel critico ({value:.1f}%).",
        True, 10,
    ),
    (
        "nivel-atencao", "level_pct", "<", 60.0,
        "consumo", "media",
        "Reservatorio em atencao ({value:.1f}%).",
        True, 10,
    ),
    # ── Pressão sensor 1 ─────────────────────────────────────────────────────
    (
        "pressao-1-baixa", "pressure1_mca", "<", 12.0,
        "pressao", "media",
        "Pressao baixa no sensor 1 ({value:.2f} MCA).",
        False, 5,
    ),
    (
        "pressao-1-alta", "pressure1_mca", ">", 45.0,
        "pressao", "alta",
        "Pressao alta no sensor 1 ({value:.2f} MCA).",
        False, 5,
    ),
    # ── Vazão ────────────────────────────────────────────────────────────────
    (
        "sem-fluxo", "flow_total_lph", "<=", 1.0,
        "sensor", "media",
        "Vazao sem fluxo no periodo atual ({value:.1f} L/h).",
        False, 10,
    ),
    (
        "vazao-baixa", "flow_total_lph", "<", 120.0,
        "consumo", "baixa",
        "Vazao baixa ({value:.1f} L/h).",
        False, 10,
    ),
    (
        "vazao-alta", "flow_total_lph", ">", 1500.0,
        "vazamento", "alta",
        "Vazao alta ({value:.1f} L/h).",
        False, 5,
    ),
    # ── Atualização ──────────────────────────────────────────────────────────
    (
        "sem-atualizacao", "data_age_minutes", ">", 120.0,
        "sensor", "alta",
        "Sem atualizacao recente de telemetria ha {value:.0f} min.",
        False, 5,
    ),
    # ── Consumo (razão 24h / 30d) ─────────────────────────────────────────────
    (
        "consumo-muito-alto", "flow_ratio_24h_30d", ">=", 1.7,
        "vazamento", "alta",
        "Possivel vazamento: consumo muito alto ({value:.2f}x da media).",
        False, 15,
    ),
    (
        "consumo-acima", "flow_ratio_24h_30d", ">=", 1.3,
        "consumo", "media",
        "Consumo acima do padrao ({value:.2f}x da media).",
        False, 15,
    ),
    (
        "consumo-abaixo", "flow_ratio_24h_30d", "<=", 0.4,
        "consumo", "baixa",
        "Consumo abaixo do esperado ({value:.2f}x da media).",
        False, 15,
    ),
    # ── Autonomia ─────────────────────────────────────────────────────────────
    (
        "autonomia-critica", "autonomy_hours", "<", 24.0,
        "consumo", "alta",
        "Autonomia critica ({value:.1f} h).",
        True, 30,
    ),
    (
        "autonomia-atencao", "autonomy_hours", "<", 72.0,
        "consumo", "media",
        "Autonomia em atencao ({value:.1f} h).",
        True, 30,
    ),
]


def upgrade() -> None:
    for row in _DEFAULT_RULES:
        (
            rule_key, metric, operator, threshold, alert_type, severity,
            message_template, requires_reservoir, hysteresis_minutes,
        ) = row
        op.execute(f"""
            INSERT INTO alert_rules
                (installation_id, rule_key, metric, operator, threshold,
                 alert_type, severity, message_template,
                 requires_reservoir, hysteresis_minutes, is_active)
            VALUES
                (NULL, '{rule_key}', '{metric}', '{operator}', {threshold},
                 '{alert_type}', '{severity}', '{message_template}',
                 {'true' if requires_reservoir else 'false'},
                 {hysteresis_minutes}, true)
            ON CONFLICT DO NOTHING
        """)


def downgrade() -> None:
    keys = ", ".join(f"'{r[0]}'" for r in _DEFAULT_RULES)
    op.execute(f"""
        DELETE FROM alert_rules
        WHERE installation_id IS NULL
          AND rule_key IN ({keys})
    """)
