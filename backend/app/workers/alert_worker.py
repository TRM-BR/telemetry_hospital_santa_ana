"""
app/workers/alert_worker.py — Motor de alertas adaptativo v3.

Ciclo (a cada worker_alert_interval_seconds):
  1. Carrega instalações ativas com dispositivos ativos.
  2. Para cada instalação executa o pipeline (transação isolada):
     a. sem_comunicacao sempre.
     b. Se dados estão velhos (>4h): encerra aqui.
     c. Failsafes absolutos (nivel<5%, autonomia<4h, sensor_invalido).
     d. Se baseline não está pronto: encerra aqui.
     e. Detectores estatísticos (consumo_acima_media, consumo_sem_repouso,
        vazao_noturna, pico_consumo, queda_nivel).
  3. Upsert alert_state + alert_events em transições (inativo→ativo, ativo→inativo).

Baselines:
  Usa apenas o baseline global por instalação + métrica, conforme o schema real
  de produção (migration 0008). Não depende de alert_rule_overrides, alert_snoozes
  nem das colunas da migration 0009.

Isolamento:
  Cada instalação roda em commit/rollback próprio. Erro numa instalação não
  aborta as demais.

Severidade: atencao | moderado | alto | critico
"""
from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.behavior import (
    period_types_for,
    to_brt,
    typical_variation_per_hour,
)
from app.alerts.capabilities import (
    InstallationCapabilities,
    consumption_metric,
    get_installation_capabilities,
)
from app.alerts.severity import (
    is_critical_severity,
    severity_from_band,
    severity_from_band_low,
    severity_from_ratio as _severity_from_ratio,
    severity_cap_by_confidence as _severity_cap_by_confidence,
    min_severity as _min_severity_new,
)
from app.services.alert_notification_service import (
    enqueue_critical_alert_user_notifications,
)
from app.alerts.signals import (
    sustained_above,
    sustained_below,
    robust_high as _robust_high,
    drop_per_hour as _drop_per_hour_smoothed,
    window_points as _window_pts,
    nights_without_rest as _nights_without_rest,
    days_since_last_rest as _days_since_last_rest,
    night_by_night_summary as _night_by_night_summary,
    max_continuous_flow_minutes as _max_continuous_flow_min,
)
from app.config import get_settings
from app.db.session import get_session
from app.logging import get_logger
from app.workers.alert_trigger import drain_dirty as _drain_dirty
from app.processing.derivations.flow_window import windowed_flow_series

logger = get_logger(__name__)

# Mínimo de vazão para considerar "fluxo existente" (L/h)
_FLOW_MIN_LPH: float = 2.0
# Detector de vazamento noturno — janela de lookback e limiar de repouso.
_LEAK_LOOKBACK_DAYS: int = 30
_REST_FLOW_THRESHOLD_LPH: float = 1.0
# Teto físico — vazão acima disso é artefato (reset de contador, etc.) → descartar
_FLOW_HARD_CAP_LPH: float = 100_000.0
# Fase 11: baseline stale quando não foi recalculado há mais de 26h.
# 24h (ciclo diário) + 2h de folga para atrasos operacionais.
_BEHAVIOR_STALE_HOURS: float = 26.0

# Fase 12 — calibragem de severidade comportamental.
# observed >= este múltiplo de anomaly_high → candidato a critico.
_CRITICAL_ANOMALY_MULTIPLIER: float = 2.0
# Duração (min) na faixa normal..anomaly p/ subir atencao→moderado.
_SUSTAINED_BAND_MODERATE_MIN: float = 120.0
# Limiares de queda da caixa — distinguem queda LEVE de FORTE/PERSISTENTE.
# pressure2: queda por hora na métrica pressure2, na unidade do sensor.
# level_pct: queda por hora em pontos percentuais (p.p./h).
_TANK_FALL_LIGHT_PRESSURE: float = 1.0    # pressure2/h (unidade do sensor), lookback 2h
_TANK_FALL_LIGHT_LEVEL: float = 5.0       # p.p./h em level_pct, lookback 2h
_TANK_FALL_LIGHT_HOURS: float = 2.0
_TANK_FALL_STRONG_PRESSURE: float = 2.0   # pressure2/h (unidade do sensor), lookback 3h
_TANK_FALL_STRONG_LEVEL: float = 10.0     # p.p./h em level_pct, lookback 3h
_TANK_FALL_STRONG_HOURS: float = 3.0
# Tolerância p/ pressure2/temperature2 "≈ 0" (ruído de sensor)
_TANK_ZERO_TOL: float = 0.5
# Persistência mínima (nº de leituras) p/ confirmar condição de caixa
_TANK_MIN_READINGS: int = 2
# Janela consolidada de consumo sustentado (min) e nº mínimo de pontos
_SUSTAINED_WINDOW_MIN: int = 60
_SUSTAINED_MIN_POINTS: int = 3
# Razão mínima atual/anterior para classificar como pico (subida rápida)
_PEAK_RISE_RATIO: float = 1.15
# Dados mais velhos que isso → stale (só sem_comunicacao roda)
_STALE_HOURS: float = 4.0

# Severidade graduada — fração da banda normal→anomalia a partir da qual a
# intensidade já justifica "moderado" (abaixo disso, "atencao").
_BAND_MODERATE_RATIO: float = 0.5

# detect_variacao_rapida — velocidade recente vs. típica da instalação.
# Dispara a partir de _VELOCITY_TRIGGER_MULT× a velocidade típica; a severidade
# escala com o múltiplo (mesma filosofia da intensidade de magnitude).
_VELOCITY_TRIGGER_MULT: float = 5.0   # gatilho = piso de moderado (sem "atencao")
_VELOCITY_MODERADO_MULT: float = 5.0
_VELOCITY_ALTO_MULT: float = 8.0
_VELOCITY_CRITICO_MULT: float = 12.0
# Janela curta (min) e nº mínimo de pontos p/ medir a velocidade recente.
_VELOCITY_WINDOW_MIN: int = 30
_VELOCITY_MIN_POINTS: int = 3
# Guarda anti-ruído: o movimento absoluto recente precisa ser ao menos esta
# fração da faixa normal do canal (normal_high − normal_low). Evita que jitter
# em canais quase-constantes dispare por divisão por velocidade típica minúscula.
_VELOCITY_MIN_DELTA_FRAC: float = 0.5

# Frações de anomaly_low que graduam o alerta de consumo anormalmente baixo
# (perfil continuous). Quanto mais perto de zero, mais grave.
_LOW_ALTO_FRAC: float = 0.25
_LOW_MODERADO_FRAC: float = 0.60


# ---------------------------------------------------------------------------
# Tipos de dados internos
# ---------------------------------------------------------------------------

@dataclass
class SeriesPoint:
    ts: datetime
    value: float


@dataclass
class InstallationContext:
    """Todos os dados para avaliar os detectores de uma instalação."""
    inst_id: int
    slug: str
    learning_mode_until: Optional[datetime]  # None = sem modo aprendizado
    baseline_ready_at: Optional[datetime]    # None = cold start
    # Série das últimas 72h por metric_name
    series: dict[str, list[SeriesPoint]] = field(default_factory=dict)
    # Baselines globais: metric_name -> {mean, std, p10, p90, ...}
    baselines: dict[str, dict[str, float]] = field(default_factory=dict)
    # Baseline comportamental: (channel_role, metric_name, period_type) → row_dict
    # Carregado na Fase 5; consultado pelos detectores a partir da Fase 7.
    behavior: dict[tuple[str, str, str], dict] = field(default_factory=dict)
    # MAX(computed_at) das linhas de baseline desta instalação.
    # None = baseline nunca calculado. Usado por detect_behavior_baseline_stale.
    behavior_last_computed: Optional[datetime] = None
    # Overrides: rule_key → {param_name → value}
    overrides: dict[str, dict[str, float]] = field(default_factory=dict)
    # Snoozes ativos: set de rule_keys silenciadas (None = todas)
    active_snoozes: set[Optional[str]] = field(default_factory=set)
    latest_ts: Optional[datetime] = None
    # Capacidades hidráulicas inferidas dos dados (nunca por slug)
    capabilities: Optional[InstallationCapabilities] = None
    # Configurações da instância (pisos de alerta, etc.)
    settings: Any = field(default=None)
    # Estado anterior por rule_key: {is_active, first_triggered_at, dados_relevantes}
    prior_alert_states: dict[str, dict] = field(default_factory=dict)
    # Série de vazão longa (30 dias) — exclusiva para detect_vazamento_noturno.
    long_series: dict[str, list[SeriesPoint]] = field(default_factory=dict)


@dataclass
class DetectorResult:
    """Resultado de um detector para uma instalação."""
    rule_key: str
    alert_type: str
    is_active: bool
    severity: Optional[str] = None
    titulo: Optional[str] = None
    mensagem_usuario: Optional[str] = None
    recomendacao: Optional[str] = None
    dados_relevantes: Optional[dict[str, Any]] = None
    current_value: Optional[float] = None
    # Motivo de inatividade/não-aplicabilidade (auditoria/debug)
    reason: Optional[str] = None


def _inactive(rule_key: str, alert_type: str, reason: str) -> "DetectorResult":
    """Resultado inativo explícito — resolve alertas antigos presos."""
    return DetectorResult(rule_key=rule_key, alert_type=alert_type,
                          is_active=False, reason=reason)


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_SQL_INSTALLATIONS = text("""
    SELECT DISTINCT
        i.id,
        i.slug,
        NULL::timestamptz AS learning_mode_until,
        NULL::timestamptz AS baseline_ready_at
    FROM installations i
    JOIN device_installations di
        ON di.installation_id = i.id
    AND di.valid_to IS NULL
    JOIN devices d
        ON d.id = di.device_id
    AND d.is_active = true
    WHERE i.is_active = true
    ORDER BY i.id
""")

_SQL_INSTALLATIONS_BY_IDS = text("""
    SELECT DISTINCT
        i.id,
        i.slug,
        NULL::timestamptz AS learning_mode_until,
        NULL::timestamptz AS baseline_ready_at
    FROM installations i
    JOIN device_installations di
        ON di.installation_id = i.id
    AND di.valid_to IS NULL
    JOIN devices d
        ON d.id = di.device_id
    AND d.is_active = true
    WHERE i.is_active = true
      AND i.id = ANY(:ids)
    ORDER BY i.id
""")

_SQL_LATEST_TS = text("""
    SELECT MAX(dm.derived_at_utc)
    FROM derived_metrics dm
    JOIN device_installations di ON di.device_id = dm.device_id
    WHERE di.installation_id = :installation_id
      AND di.valid_to IS NULL
""")

# Marca de INGESTÃO (created_at, não derived_at_utc). Quando o Dragino trava e
# despeja um burst com leituras de timestamp PASSADO, derived_at_utc pode não
# avançar, mas created_at sim — então o histórico atrasado força a reavaliação.
# Restrito à janela de 72h (mesma das séries) para limitar o custo e usar o
# índice (installation_id, derived_at_utc).
_SQL_LATEST_INGEST = text("""
    SELECT MAX(dm.created_at)
    FROM derived_metrics dm
    JOIN device_installations di ON di.device_id = dm.device_id
    WHERE di.installation_id = :installation_id
      AND di.valid_to IS NULL
      AND dm.derived_at_utc >= now() - INTERVAL '72 hours'
""")

_SQL_SERIES = text("""
    SELECT dm.metric_name, dm.value, dm.derived_at_utc
    FROM derived_metrics dm
    JOIN device_installations di ON di.device_id = dm.device_id
    WHERE di.installation_id = :installation_id
      AND di.valid_to IS NULL
      AND dm.metric_name IN (
          'level_pct', 'autonomia_dias',
          'pressure', 'pressure2', 'temperature2'
      )
      AND dm.derived_at_utc >= now() - INTERVAL '72 hours'
    ORDER BY dm.metric_name, dm.derived_at_utc ASC
""")

# Contadores acumulados para cálculo de vazão por janela de 1h.
# 73h = 72h úteis + 1h de margem para o primeiro ponto da janela.
# Usa parsed_measurements diretamente (tem installation_id, sem join necessário).
_SQL_COUNTS = text("""
    SELECT pm.collected_at_utc, pm.count_pulses, pm.count2_pulses
    FROM parsed_measurements pm
    WHERE pm.installation_id = :installation_id
      AND pm.collected_at_utc >= now() - INTERVAL '73 hours'
    ORDER BY pm.collected_at_utc ASC
""")

# Janela longa exclusiva do detector de vazamento noturno (30 dias).
# Mantém _SQL_COUNTS (73h) intocado — os demais detectores dependem da janela curta.
_SQL_COUNTS_LEAK = text(f"""
    SELECT pm.collected_at_utc, pm.count_pulses, pm.count2_pulses
    FROM parsed_measurements pm
    WHERE pm.installation_id = :installation_id
      AND pm.collected_at_utc >= now() - INTERVAL '{_LEAK_LOOKBACK_DAYS} days'
    ORDER BY pm.collected_at_utc ASC
""")

_SQL_BASELINES = text("""
    SELECT metric_name, mean, std, p10, p90, sample_count, window_days, computed_at
    FROM metric_baselines
    WHERE installation_id = :installation_id
""")

# Carrega baseline comportamental por instalação (Fase 5+).
# computed_at incluso para detect_behavior_baseline_stale (Fase 11).
_SQL_BEHAVIOR = text("""
    SELECT channel_role, metric_name, period_type,
           normal_low, normal_high, anomaly_low, anomaly_high,
           minimum_night_flow, profile_type, confidence,
           zero_ratio, near_zero_ratio, p50, p90, sample_count,
           typical_variation_per_hour,
           computed_at
    FROM installation_behavior_baselines
    WHERE installation_id = :installation_id
""")

_SQL_STATES = text("""
    SELECT rule_key, is_active, first_triggered_at, last_triggered_at,
           last_resolved_at, current_value, severity, dados_relevantes
    FROM alert_state
    WHERE installation_id = :installation_id
""")

_SQL_UPSERT_STATE = text("""
    INSERT INTO alert_state (
        installation_id, rule_key, is_active,
        alert_type, severity, titulo, mensagem_usuario, recomendacao,
        dados_relevantes, current_value,
        first_triggered_at, last_triggered_at, last_resolved_at,
        updated_at
    ) VALUES (
        :installation_id, :rule_key, :is_active,
        :alert_type, :severity, :titulo, :mensagem_usuario, :recomendacao,
        CAST(:dados_relevantes AS jsonb), :current_value,
        :first_triggered_at, :last_triggered_at, :last_resolved_at,
        now()
    )
    ON CONFLICT (installation_id, rule_key) DO UPDATE SET
        is_active           = EXCLUDED.is_active,
        alert_type          = EXCLUDED.alert_type,
        severity            = CASE WHEN EXCLUDED.is_active THEN EXCLUDED.severity
                                   ELSE alert_state.severity END,
        titulo              = CASE WHEN EXCLUDED.is_active THEN EXCLUDED.titulo
                                   ELSE alert_state.titulo END,
        mensagem_usuario    = CASE WHEN EXCLUDED.is_active THEN EXCLUDED.mensagem_usuario
                                   ELSE alert_state.mensagem_usuario END,
        recomendacao        = CASE WHEN EXCLUDED.is_active THEN EXCLUDED.recomendacao
                                   ELSE alert_state.recomendacao END,
        dados_relevantes    = CASE WHEN EXCLUDED.is_active THEN EXCLUDED.dados_relevantes
                                   ELSE alert_state.dados_relevantes END,
        current_value       = EXCLUDED.current_value,
        first_triggered_at  = CASE
            WHEN EXCLUDED.is_active
                 AND (NOT alert_state.is_active OR alert_state.first_triggered_at IS NULL)
            THEN EXCLUDED.first_triggered_at
            ELSE alert_state.first_triggered_at
        END,
        last_triggered_at   = CASE
            WHEN EXCLUDED.is_active THEN EXCLUDED.last_triggered_at
            ELSE alert_state.last_triggered_at
        END,
        last_resolved_at    = CASE
            WHEN NOT EXCLUDED.is_active AND alert_state.is_active THEN now()
            ELSE alert_state.last_resolved_at
        END,
        updated_at          = now()
""")

_SQL_INSERT_EVENT = text("""
    INSERT INTO alert_events (
        installation_id, rule_key, alert_type, severity,
        message, titulo, mensagem_usuario, recomendacao,
        dados_relevantes, status, current_value, triggered_at
    ) VALUES (
        :installation_id, :rule_key, :alert_type, :severity,
        :message, :titulo, :mensagem_usuario, :recomendacao,
        CAST(:dados_relevantes AS jsonb), :status, :current_value, now()
    )
    RETURNING id
""")

_SQL_UPDATE_ACTIVE_EVENT = text("""
    UPDATE alert_events SET
        severity          = :severity,
        titulo            = :titulo,
        mensagem_usuario  = :mensagem_usuario,
        recomendacao      = :recomendacao,
        message           = :message,
        dados_relevantes  = CAST(:dados_relevantes AS jsonb),
        current_value     = :current_value,
        updated_at        = now()
    WHERE id = (
        SELECT id FROM alert_events
        WHERE installation_id = :installation_id
          AND rule_key         = :rule_key
          AND status           = 'ativo'
          AND (
              (
                  CAST(:metric_used AS text) IS NULL
                  AND (
                      NOT (dados_relevantes ? 'metric_used')
                      OR dados_relevantes->>'metric_used' IS NULL
                      OR dados_relevantes->>'metric_used' = ''
                  )
              )
              OR (
                  CAST(:metric_used AS text) IS NOT NULL
                  AND dados_relevantes->>'metric_used' = CAST(:metric_used AS text)
              )
          )
        ORDER BY triggered_at DESC, id DESC
        LIMIT 1
    )
""")


# ---------------------------------------------------------------------------
# Helpers de série e baseline
# ---------------------------------------------------------------------------

def _last(series: list[SeriesPoint]) -> Optional[float]:
    return series[-1].value if series else None


def _window_points(series: list[SeriesPoint], minutes: int,
                   now: datetime) -> list[SeriesPoint]:
    """Pontos dentro da janela dos últimos 'minutes' minutos."""
    cutoff = now.timestamp() - minutes * 60
    return [p for p in series if p.ts.timestamp() >= cutoff]


def _last_n(series: list[SeriesPoint], n: int) -> list[float]:
    """Últimos n valores (série já ordenada ascendentemente por ts)."""
    return [p.value for p in series[-n:]] if series else []


def _clean_flow(series: list[SeriesPoint]) -> list[SeriesPoint]:
    """
    Remove pontos não confiáveis de uma série de vazão:
    não-finitos, negativos (delta de contador resetado) e acima do teto físico.
    """
    out: list[SeriesPoint] = []
    for p in series:
        v = p.value
        if v is None or not math.isfinite(v):
            continue
        if v < 0 or v > _FLOW_HARD_CAP_LPH:
            continue
        out.append(p)
    return out


def _peak_point(points: list[SeriesPoint]) -> Optional[SeriesPoint]:
    return max(points, key=lambda p: p.value) if points else None


def _is_falling(series: list[SeriesPoint], min_drop_per_hour: float,
                lookback_hours: float, now: datetime) -> bool:
    """True se a série está em queda sustentada >= min_drop_per_hour p.p./h."""
    drop = _drop_per_hour(series, lookback_hours=lookback_hours, now=now)
    return drop is not None and drop >= min_drop_per_hour


def _tank_sensor_failed(ctx: "InstallationContext") -> bool:
    """
    True se as últimas leituras indicam FALHA do sensor da caixa
    (pressure2 ≈ 0 E temperature2 ≈ 0). Usado para suprimir alertas de nível
    que seriam baseados em leitura inválida.
    """
    p2 = _last_n(ctx.series.get("pressure2", []), _TANK_MIN_READINGS)
    t2 = _last_n(ctx.series.get("temperature2", []), _TANK_MIN_READINGS)
    if len(p2) < _TANK_MIN_READINGS or len(t2) < _TANK_MIN_READINGS:
        return False
    return (all(abs(v) <= _TANK_ZERO_TOL for v in p2)
            and all(abs(v) <= _TANK_ZERO_TOL for v in t2))


def _coverage_above_for_hours(series: list[SeriesPoint], threshold: float,
                               hours: float, now: datetime,
                               min_coverage: float = 0.95) -> bool:
    """True se ≥ min_coverage dos pontos nos últimos 'hours' h estão acima de threshold."""
    cutoff = now.timestamp() - hours * 3600
    window = [p for p in series if p.ts.timestamp() >= cutoff]
    if not window:
        return False
    above = sum(1 for p in window if p.value > threshold)
    return (above / len(window)) >= min_coverage


def _drop_per_hour(series: list[SeriesPoint], lookback_hours: float = 1.5,
                   now: Optional[datetime] = None) -> Optional[float]:
    """Regressão linear: queda de level_pct por hora. Positivo = queda."""
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - lookback_hours * 3600
    window = [p for p in series if p.ts.timestamp() >= cutoff]
    if len(window) < 3:
        return None
    ts_ref = window[0].ts.timestamp()
    xs = [(p.ts.timestamp() - ts_ref) / 3600 for p in window]
    ys = [p.value for p in window]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return -(num / den)  # positivo = queda


def _night_values(series: list[SeriesPoint], now: datetime) -> list[float]:
    """Vazões nas horas noturnas (00–06h BRT) das últimas 24h."""
    cutoff = now.timestamp() - 24 * 3600
    vals = []
    for p in series:
        if p.ts.timestamp() < cutoff:
            continue
        local_hour = (p.ts.hour - 3) % 24
        if 0 <= local_hour < 6:
            vals.append(p.value)
    return vals


def _night_flow_mean(series: list[SeriesPoint], now: datetime) -> Optional[float]:
    """Média da vazão noturna (00–06h BRT, últimas 24h)."""
    vals = _night_values(series, now)
    return sum(vals) / len(vals) if vals else None


def _night_flow_min(series: list[SeriesPoint], now: datetime) -> Optional[float]:
    """Menor vazão noturna (00–06h BRT, últimas 24h)."""
    vals = _night_values(series, now)
    return min(vals) if vals else None


def _get_param(overrides: dict[str, dict[str, float]],
               rule_key: str, param: str, default: float) -> float:
    return overrides.get(rule_key, {}).get(param, default)


# Ordenação de severidade (menor índice = mais conservador). Sem "atencao".
_SEV_ORDER: dict[str, int] = {"moderado": 0, "alto": 1, "critico": 2}


def _min_severity(a: str, b: str) -> str:
    """Retorna a severidade mais conservadora (menor) das duas."""
    return a if _SEV_ORDER.get(a, 0) <= _SEV_ORDER.get(b, 2) else b


def _max_severity(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Retorna a severidade mais grave das duas. None se ambas forem None."""
    if a is None:
        return b
    if b is None:
        return a
    return a if _SEV_ORDER.get(a, 0) >= _SEV_ORDER.get(b, 0) else b


# ---------------------------------------------------------------------------
# Helpers de baseline comportamental (carregados na Fase 5)
# ---------------------------------------------------------------------------

def behavior_ref(
    ctx: "InstallationContext",
    channel_role: str,
    metric: str,
    period: str,
) -> Optional[dict]:
    """
    Retorna a linha de baseline comportamental para o canal/métrica/período
    desta instalação, ou None se não houver baseline.

    Uso esperado (Fase 7):
        ref = behavior_ref(ctx, "tank_outlet", "flow2_lph", "overall")
        if ref and observed > ref["anomaly_high"]: ...
    """
    return ctx.behavior.get((channel_role, metric, period))


def severity_cap_by_confidence(conf: str) -> str:
    """
    Teto de severidade permitido pela confiança do baseline (relatório 10.6).
    Definido na Fase 5; usado pelos detectores a partir da Fase 7.

        low          → teto: "moderado"
        medium       → teto: "alto"
        high         → teto: "critico"
        consolidated → teto: "critico"
    """
    return {
        "low":          "moderado",
        "medium":       "alto",
        "high":         "critico",
        "consolidated": "critico",
    }.get(conf, "moderado")


# ---------------------------------------------------------------------------
# Fase 12 — Calibragem de severidade e mensagens comportamentais
# ---------------------------------------------------------------------------

def _fmt(v: Optional[float]) -> str:
    """Formata número com vírgula decimal (pt-BR), 1 casa. None → '—'."""
    if v is None:
        return "—"
    return f"{v:.1f}".replace(".", ",")


def _fmt_pct(v: Optional[float]) -> str:
    """Formata percentual inteiro (pt-BR). None → '—'."""
    if v is None:
        return "—"
    return f"{v:.0f}"


# Tradução curta dos códigos de severity_reason → frase para o bullet "Classificação".
_SEVERITY_REASON_LABELS: dict[str, str] = {
    "within_normal_profile":            "dentro do padrão normal da instalação",
    "band":                             "acima do normal, abaixo do limite de anomalia",
    "band_high_intensity":              "bem acima do normal, perto do limite de anomalia",
    "band_sustained":                   "acima do normal de forma sustentada",
    "band_light_composite":             "acima do normal com queda leve da caixa",
    "band_strong_composite":            "acima do normal com queda forte/persistente da caixa",
    "above_anomaly":                    "ultrapassou o limite de anomalia da instalação",
    "above_anomaly_light_composite":    "ultrapassou a anomalia com queda leve da caixa",
    "at_least_2x_anomaly":              "atingiu 2x ou mais o limite de anomalia",
    "strong_composite_evidence":        "anomalia com queda forte/persistente da caixa",
    "above_anomaly_safe_tank_level":    "taxa de queda acima do anômalo, mas nível ainda em faixa segura",
    "above_anomaly_low_tank_level":     "taxa de queda acima do anômalo com nível já baixo",
}


def _excess_fields(
    observed: float,
    normal_high: Optional[float],
    anomaly_high: Optional[float],
) -> dict[str, Optional[float]]:
    """
    Calcula o excesso (absoluto e percentual) sobre os limites comportamentais.
    pct = None quando o divisor é ausente ou <= 0.
    """
    eon = observed - normal_high if normal_high is not None else None
    eon_pct = (
        (eon / normal_high * 100.0)
        if (eon is not None and normal_high and normal_high > 0) else None
    )
    eoa = observed - anomaly_high if anomaly_high is not None else None
    eoa_pct = (
        (eoa / anomaly_high * 100.0)
        if (eoa is not None and anomaly_high and anomaly_high > 0) else None
    )
    return {
        "excess_over_normal":      round(eon, 1) if eon is not None else None,
        "excess_over_normal_pct":  round(eon_pct, 0) if eon_pct is not None else None,
        "excess_over_anomaly":     round(eoa, 1) if eoa is not None else None,
        "excess_over_anomaly_pct": round(eoa_pct, 0) if eoa_pct is not None else None,
    }


def _tank_fall_evidence(
    ctx: InstallationContext,
    now: datetime,
) -> tuple[bool, bool, list[str]]:
    """
    Avalia queda de nível/pressão da caixa em dois níveis (Fase 12).

    Retorna (has_composite, has_strong_composite, factors):
      - leve : pressure2 ou level_pct caindo nos limiares LIGHT (lookback 2h).
      - forte: pressure2 ou level_pct caindo nos limiares STRONG (lookback 3h).
    has_strong implica has_composite. `factors` descreve os sinais detectados.
    """
    cap = ctx.capabilities
    if cap is None or not cap.has_tank_pressure:
        return False, False, []

    p2 = ctx.series.get("pressure2", [])
    lvl = ctx.series.get("level_pct", [])

    factors: list[str] = []
    strong = False
    composite = False

    # Pressão da caixa
    if _is_falling(p2, _TANK_FALL_STRONG_PRESSURE, _TANK_FALL_STRONG_HOURS, now):
        factors.append("tank_pressure_falling_strong")
        strong = True
        composite = True
    elif _is_falling(p2, _TANK_FALL_LIGHT_PRESSURE, _TANK_FALL_LIGHT_HOURS, now):
        factors.append("tank_pressure_falling")
        composite = True

    # Nível da caixa
    if _is_falling(lvl, _TANK_FALL_STRONG_LEVEL, _TANK_FALL_STRONG_HOURS, now):
        factors.append("tank_level_falling_strong")
        strong = True
        composite = True
    elif _is_falling(lvl, _TANK_FALL_LIGHT_LEVEL, _TANK_FALL_LIGHT_HOURS, now):
        factors.append("tank_level_falling")
        composite = True

    return composite, strong, factors


def _severity_from_behavior(
    *,
    observed: float,
    normal_high: Optional[float],
    anomaly_high: Optional[float],
    baseline_confidence: str,
    has_composite_evidence: bool = False,
    has_strong_composite_evidence: bool = False,
    duration_minutes: Optional[float] = None,
    detector_key: str,
    profile_type: Optional[str] = None,
) -> tuple[Optional[str], str]:
    """
    Regra central de severidade comportamental — graduada por INTENSIDADE.

    Retorna (severity, severity_reason_code). severity=None → não alertar.

    Princípios:
      - observed <= normal_high → não alerta (gatilho inalterado).
      - A criticidade escala com a INTENSIDADE da ultrapassagem:
          * banda normal→anomalia: band_ratio (0..1) eleva atencao→moderado;
          * acima da anomalia: over = observed/anomaly_high eleva alto→critico
            (critico a partir de _CRITICAL_ANOMALY_MULTIPLIER).
      - Evidência composta FORTE eleva dentro da faixa; composta LEVE só na banda.
      - Sustentação prolongada na banda também eleva atencao→moderado.
      - Teto por confiança: low→moderado, medium→alto, high/consolidated→critico.
    """
    if normal_high is None or anomaly_high is None:
        return None, "incomplete_baseline"
    if observed <= normal_high:
        return None, "within_normal_profile"

    if observed <= anomaly_high:
        # Banda normal→anomalia: intensidade relativa dentro da banda.
        span = anomaly_high - normal_high
        band_ratio = (observed - normal_high) / span if span > 0 else 1.0
        if has_strong_composite_evidence:
            raw, reason = "alto", "band_strong_composite"
        elif has_composite_evidence:
            raw, reason = "moderado", "band_light_composite"
        elif band_ratio >= _BAND_MODERATE_RATIO:
            raw, reason = "moderado", "band_high_intensity"
        elif duration_minutes is not None and duration_minutes >= _SUSTAINED_BAND_MODERATE_MIN:
            raw, reason = "moderado", "band_sustained"
        else:
            # Banda inferior sem evidência: não dispara (sem "atencao").
            return None, "band_low_intensity"
    else:
        # Acima da anomalia: intensidade = quantas vezes o limite anômalo.
        over = observed / anomaly_high if anomaly_high > 0 else 1.0
        if over >= _CRITICAL_ANOMALY_MULTIPLIER:
            raw, reason = "critico", "at_least_2x_anomaly"
        elif has_strong_composite_evidence:
            raw, reason = "critico", "strong_composite_evidence"
        elif has_composite_evidence:
            raw, reason = "alto", "above_anomaly_light_composite"
        else:
            raw, reason = "alto", "above_anomaly"

    # Teto por confiança da baseline.
    capped = _min_severity(raw, severity_cap_by_confidence(baseline_confidence))
    if capped != raw:
        reason += f"|capped_{baseline_confidence}"
    return capped, reason


def _severity_from_multiple(
    multiple: float,
    baseline_confidence: str,
    *,
    t_moderado: float,
    t_alto: float,
    t_critico: float,
    reason_prefix: str,
) -> tuple[str, str]:
    """
    Severidade graduada a partir de um múltiplo adimensional (ex.: velocidade
    recente / velocidade típica). Quanto maior o múltiplo, mais grave. Aplica o
    teto por confiança da baseline. Pressupõe que o gatilho já foi atingido.
    """
    if multiple >= t_critico:
        raw, reason = "critico", f"{reason_prefix}_critico"
    elif multiple >= t_alto:
        raw, reason = "alto", f"{reason_prefix}_alto"
    else:
        raw, reason = "moderado", f"{reason_prefix}_moderado"
    capped = _min_severity(raw, severity_cap_by_confidence(baseline_confidence))
    if capped != raw:
        reason += f"|capped_{baseline_confidence}"
    return capped, reason


def _recommendation_by_severity(severity: str) -> str:
    """Recomendação proporcional à severidade."""
    return {
        "moderado": "Verificar pontos de uso e horários de consumo.",
        "alto":     "Inspecionar a instalação em campo.",
        "critico":  "Ação imediata: risco operacional.",
    }.get(severity, "Verificar pontos de uso e horários de consumo.")


def _behavior_message(
    *,
    channel_label: str,
    observed: float,
    unit: str,
    normal_high: Optional[float],
    anomaly_high: Optional[float],
    excess: dict[str, Optional[float]],
    period_type: str,
    baseline_confidence: str,
    severity: str,
    severity_reason: str,
    composite_factors: list[str],
    duration_minutes: Optional[float],
) -> str:
    """
    Monta mensagem_usuario em TÓPICOS (bullets '• ', separados por '\\n').
    Campos numéricos também ficam em dados_relevantes (estruturados p/ Fase 13/14).
    """
    lines: list[str] = []
    lines.append(f"• Canal: {channel_label}")
    lines.append(f"• Valor observado: {_fmt(observed)} {unit}")
    if normal_high is not None:
        lines.append(f"• Normal esperado ({period_type}): até {_fmt(normal_high)} {unit}")
    if anomaly_high is not None:
        lines.append(f"• Limite de anomalia: acima de {_fmt(anomaly_high)} {unit}")
    if excess.get("excess_over_normal") is not None:
        eon = excess["excess_over_normal"]
        eon_pct = excess.get("excess_over_normal_pct")
        pct_str = f" (+{_fmt_pct(eon_pct)}%)" if eon_pct is not None else ""
        lines.append(f"• Excesso sobre o normal: +{_fmt(eon)} {unit}{pct_str}")
    if excess.get("excess_over_anomaly") is not None and (excess["excess_over_anomaly"] or 0) > 0:
        eoa = excess["excess_over_anomaly"]
        eoa_pct = excess.get("excess_over_anomaly_pct")
        pct_str = f" (+{_fmt_pct(eoa_pct)}%)" if eoa_pct is not None else ""
        lines.append(f"• Excesso sobre a anomalia: +{_fmt(eoa)} {unit}{pct_str}")
    if duration_minutes is not None:
        if duration_minutes >= 60:
            dur = f"{duration_minutes / 60:.0f}h".replace(".", ",")
        else:
            dur = f"{duration_minutes:.0f} min"
        lines.append(f"• Duração/janela: {dur}")
    if composite_factors:
        lines.append(f"• Evidência composta: {', '.join(composite_factors)}")
    else:
        lines.append("• Sem evidência composta (nível/pressão estáveis)")
    lines.append(f"• Confiança da baseline: {baseline_confidence}")
    motivo = _SEVERITY_REASON_LABELS.get(severity_reason.split("|")[0], severity_reason)
    lines.append(f"• Classificação: {severity} — {motivo}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Shadow mode — comparação comportamental (Fase 6, sem alterar alertas)
# ---------------------------------------------------------------------------

# Detectores elegíveis para comparação shadow (Fase 6 — legado vs comportamental).
_SHADOW_DETECTOR_KEYS: frozenset[str] = frozenset({
    "consumo_acima_media",
    "pico_consumo",
    "consumo_sem_repouso",
    "vazao_noturna",
    "vazamento_pos_caixa",
})

# Detectores em shadow-only: pipeline avalia normalmente mas NÃO grava em
# alert_state/alert_events. Só emite log estruturado (alert_worker.shadow_fire).
# Usar enquanto o detector é novo e precisa de 24-48h de observação antes de
# virar alerta visível. Remover a rule_key daqui para ativar como alerta real.
_SHADOW_ONLY_RULES: frozenset[str] = frozenset({
    "variacao_rapida",
})


def _shadow_log_compare(
    log: Any,
    worker_name: str,
    ctx: InstallationContext,
    now: datetime,
    detector_results: list[DetectorResult],
) -> None:
    """
    Fase 6 — Computa a decisão comportamental em paralelo para os 5 detectores
    de consumo/vazão e loga a comparação com a decisão legada.

    Não grava em alert_state nem alert_events. A decisão real continua sendo
    a do motor legado até a Fase 7.

    Caso-chave esperado: Parque Caixa →
        rule_key=vazamento_pos_caixa  legacy_active=True  shadow_active=False
        shadow_reason=within_normal_profile (flow 6 L/h <= normal_high ~6 L/h)
    """
    cap = ctx.capabilities
    if cap is None or not ctx.behavior:
        return

    metric = consumption_metric(cap)
    if metric is None:
        return

    channel_role = _channel_role(metric)

    for det in detector_results:
        if det.rule_key not in _SHADOW_DETECTOR_KEYS:
            continue

        # Período relevante: "night" para vazao_noturna; "overall" para os demais
        # ("overall" é sempre calculado se a baseline existe para o canal).
        period = "night" if det.rule_key == "vazao_noturna" else "overall"

        ref = behavior_ref(ctx, channel_role, metric, period)
        observed = det.current_value

        # ── Decisão sombra ───────────────────────────────────────────────────
        shadow_active: bool = False
        shadow_severity: Optional[str] = None
        shadow_reason: str

        if ref is None:
            shadow_reason = "no_behavior_baseline"
        elif observed is None:
            shadow_reason = "no_observed_value"
        else:
            normal_high  = ref.get("normal_high")
            anomaly_high = ref.get("anomaly_high")
            conf         = ref.get("confidence", "low")
            profile      = ref.get("profile_type")

            if normal_high is None or anomaly_high is None:
                shadow_reason = "incomplete_baseline"
            elif profile == "continuous" and det.rule_key == "consumo_sem_repouso":
                # Perfil contínuo é normal para esta instalação: ausência de
                # repouso não é anomalia. Sem alerta shadow.
                shadow_reason = "continuous_flow_profile_normal"
            elif observed <= normal_high:
                shadow_reason = "within_normal_profile"
            elif observed > anomaly_high:
                shadow_active    = True
                shadow_severity  = severity_cap_by_confidence(conf)
                shadow_reason    = "above_anomaly_high"
            else:
                # Entre normal_high e anomaly_high → atenção conservadora.
                shadow_active    = True
                shadow_severity  = "atencao"
                shadow_reason    = "between_normal_and_anomaly"

        log.info(
            f"{worker_name}.shadow_compare",
            installation=ctx.slug,
            rule_key=det.rule_key,
            legacy_active=det.is_active,
            legacy_severity=det.severity if det.is_active else None,
            shadow_active=shadow_active,
            shadow_severity=shadow_severity,
            shadow_reason=shadow_reason,
            observed_value=(
                round(observed, 2) if isinstance(observed, float) else observed
            ),
            normal_high=(
                round(ref["normal_high"], 2)
                if ref and ref.get("normal_high") is not None else None
            ),
            anomaly_high=(
                round(ref["anomaly_high"], 2)
                if ref and ref.get("anomaly_high") is not None else None
            ),
            baseline_confidence=ref.get("confidence") if ref else None,
            period_type=period,
            profile_type=ref.get("profile_type") if ref else None,
            channel_role=channel_role,
            metric_used=metric,
        )


# ---------------------------------------------------------------------------
# Detectores
# ---------------------------------------------------------------------------

# ── 1. sem_comunicacao ────────────────────────────────────────────────────────

def detect_sem_comunicacao(ctx: InstallationContext, now: datetime) -> DetectorResult:
    result = DetectorResult(rule_key="sem_comunicacao",
                            alert_type="sensor", is_active=False)
    if ctx.latest_ts is None:
        return result

    age_min = (now - ctx.latest_ts).total_seconds() / 60.0
    result.current_value = age_min
    result.dados_relevantes = {
        "age_minutes": round(age_min, 1),
        "ultima_leitura": ctx.latest_ts.isoformat(),
        "event_time": ctx.latest_ts.isoformat(),
    }

    # Limiares calibrados para ciclo de ~2h dos dispositivos em campo
    if age_min >= 24 * 60:
        result.is_active = True
        result.severity = "critico"
        result.titulo = "Dispositivo sem comunicação — monitoramento interrompido"
        result.mensagem_usuario = (
            f"Último dado recebido há {age_min / 60:.0f}h. "
            "Nenhuma telemetria disponível."
        )
        result.recomendacao = (
            "Verificar alimentação, conexão MQTT e estado físico do dispositivo."
        )
    elif age_min >= 12 * 60:
        result.is_active = True
        result.severity = "alto"
        result.titulo = "Comunicação perdida há mais de 12h"
        result.mensagem_usuario = f"Último dado recebido há {age_min / 60:.1f}h."
        result.recomendacao = "Verificar conexão do dispositivo."
    elif age_min >= 6 * 60:
        result.is_active = True
        result.severity = "moderado"
        result.titulo = "Dispositivo sem comunicação há mais de 6h"
        result.mensagem_usuario = f"Último dado recebido há {age_min / 60:.1f}h."
        result.recomendacao = "Verificar se o dispositivo está online."

    return result


# ── 2. nivel_baixo (failsafe + progressivo) ───────────────────────────────────

def detect_nivel_baixo(ctx: InstallationContext) -> DetectorResult:
    cap = ctx.capabilities
    if cap is None or not cap.can_alert_level:
        return _inactive("nivel_baixo", "nivel",
                         "not_applicable_without_tank_pressure")
    if _tank_sensor_failed(ctx):
        return _inactive("nivel_baixo", "nivel", "tank_sensor_fault")

    result = DetectorResult(rule_key="nivel_baixo", alert_type="nivel",
                            is_active=False)
    series = ctx.series.get("level_pct", [])
    if not series:
        return result
    nivel_current = _last(series)
    if nivel_current is None:
        return result

    # Persistência: confirma com a média dos últimos ≤3 pontos.
    # Evita piscar por spike isolado de sensor; usa o pior caso (mínimo)
    # entre a média e o último ponto para não ignorar quedas reais.
    recent_vals = _last_n(series, 3)
    nivel_avg = sum(recent_vals) / len(recent_vals)
    nivel = min(nivel_current, nivel_avg)

    result.current_value = nivel_current
    result.dados_relevantes = {"level_pct": round(nivel_current, 1), "level_pct_avg3": round(nivel, 1)}

    thr_critico  = _get_param(ctx.overrides, "nivel_baixo", "thr_critico",  5.0)
    thr_alto     = _get_param(ctx.overrides, "nivel_baixo", "thr_alto",    10.0)
    thr_moderado = _get_param(ctx.overrides, "nivel_baixo", "thr_moderado", 20.0)

    if nivel < thr_critico:
        result.is_active = True
        result.severity = "critico"
        result.titulo = "Risco de interrupção do abastecimento"
        result.mensagem_usuario = (
            f"Reservatório em {nivel:.1f}% — abaixo do mínimo operacional de "
            f"{thr_critico:.0f}%."
        )
        result.recomendacao = "Acionar abastecimento de emergência imediatamente."
    elif nivel < thr_alto:
        result.is_active = True
        result.severity = "alto"
        result.titulo = "Abastecimento em risco nas próximas horas"
        result.mensagem_usuario = (
            f"Reservatório em {nivel:.1f}% — autonomia extremamente reduzida."
        )
        result.recomendacao = "Agendar reabastecimento urgente hoje."
    elif nivel < thr_moderado:
        result.is_active = True
        result.severity = "moderado"
        result.titulo = "Nível do reservatório abaixo do recomendado"
        result.mensagem_usuario = (
            f"Reservatório em {nivel:.1f}%. Reabastecimento necessário em breve."
        )
        result.recomendacao = "Planejar reabastecimento."

    return result


# ── 3. autonomia_insuficiente (failsafe + progressivo) ────────────────────────

def detect_autonomia_insuficiente(ctx: InstallationContext) -> DetectorResult:
    cap = ctx.capabilities
    if cap is None or not cap.can_alert_level:
        return _inactive("autonomia_insuficiente", "nivel",
                         "not_applicable_without_tank_pressure")
    if _tank_sensor_failed(ctx):
        return _inactive("autonomia_insuficiente", "nivel", "tank_sensor_fault")

    result = DetectorResult(rule_key="autonomia_insuficiente",
                            alert_type="nivel", is_active=False)
    series = ctx.series.get("autonomia_dias", [])
    if not series:
        return result
    autonomia_current = _last(series)
    if autonomia_current is None:
        return result

    # Persistência: confirma com a média dos últimos ≤3 pontos (pior caso).
    recent_vals = _last_n(series, 3)
    autonomia_avg = sum(recent_vals) / len(recent_vals)
    autonomia = min(autonomia_current, autonomia_avg)

    result.current_value = autonomia_current
    result.dados_relevantes = {"autonomia_dias": round(autonomia_current, 2), "autonomia_avg3": round(autonomia, 3)}

    thr_critico  = _get_param(ctx.overrides, "autonomia_insuficiente", "thr_critico",  4 / 24)
    thr_alto     = _get_param(ctx.overrides, "autonomia_insuficiente", "thr_alto",     1.0)
    thr_moderado = _get_param(ctx.overrides, "autonomia_insuficiente", "thr_moderado", 2.0)

    horas = autonomia * 24
    if autonomia < thr_critico:
        result.is_active = True
        result.severity = "critico"
        result.titulo = f"Esgotamento do reservatório em menos de {thr_critico * 24:.0f} horas"
        result.mensagem_usuario = (
            f"Autonomia estimada: {horas:.1f}h ao consumo atual."
        )
        result.recomendacao = "Acionar abastecimento de emergência imediatamente."
    elif autonomia < thr_alto:
        result.is_active = True
        result.severity = "alto"
        result.titulo = "Reservatório durará menos de 24 horas"
        result.mensagem_usuario = f"Autonomia estimada: {horas:.1f}h ao consumo atual."
        result.recomendacao = "Agendar reabastecimento urgente hoje."
    elif autonomia < thr_moderado:
        result.is_active = True
        result.severity = "moderado"
        result.titulo = "Reservatório com menos de 2 dias de autonomia"
        result.mensagem_usuario = (
            f"Autonomia estimada: {autonomia:.1f} dias ao consumo atual."
        )
        result.recomendacao = "Planejar reabastecimento em 24h."

    return result


# ── 4. sensor_invalido (failsafe — valores fisicamente impossíveis) ───────────

def detect_sensor_invalido(ctx: InstallationContext) -> DetectorResult:
    result = DetectorResult(rule_key="sensor_invalido",
                            alert_type="sensor", is_active=False)
    cap = ctx.capabilities

    # pressure1 é sempre verificável (limite físico). pressure2/level só fazem
    # sentido onde há capacidade de caixa — senão pressure2=0 é normal, não anomalia.
    checks = [("pressure", -1.0, 250.0)]
    if cap is not None and cap.has_tank_pressure:
        checks += [("pressure2", -1.0, 250.0), ("level_pct", -0.5, 100.5)]

    anomalias = []
    for metric, lo, hi in checks:
        s = ctx.series.get(metric, [])
        last = _last(s)
        if last is not None and (last < lo or last > hi):
            anomalias.append(f"{metric}={last:.2f}")

    if not anomalias:
        return result

    result.is_active = True
    result.severity = "critico"
    result.titulo = "Leitura de sensor fisicamente impossível"
    result.mensagem_usuario = (
        "Valores fora dos limites físicos detectados: "
        + ", ".join(anomalias)
        + ". Possível falha de sensor ou erro de calibração."
    )
    result.recomendacao = (
        "Verificar calibração e estado físico dos sensores. "
        "Dados de telemetria não são confiáveis até resolução."
    )
    result.dados_relevantes = {"anomalias": anomalias}
    return result


# ── helpers de canal/evidência p/ detectores de consumo ──────────────────────

def _channel_role(metric: Optional[str]) -> str:
    if metric == "flow2_lph":
        return "tank_outlet"
    if metric == "flow1_lph":
        return "street_inlet"
    return "unknown"


def _channel_label(metric: Optional[str]) -> str:
    if metric == "flow2_lph":
        return "saída da caixa"
    if metric == "flow1_lph":
        return "entrada da rua"
    return "consumo"


def _behavior_dados(
    ref: dict[str, Any],
    metric: str,
    period: str,
    observed: float,
    pts: list[SeriesPoint],
    *,
    reason: str,
    severity_reason: str,
    excess: dict[str, Optional[float]],
    composite_evidence: bool,
    strong_composite_evidence: bool,
    composite_evidence_factors: list[str],
    duration_minutes: Optional[float] = None,
    points_confirming: Optional[int] = None,
) -> dict[str, Any]:
    """
    Monta dados_relevantes comportamental completo (Fase 12).
    Campos numéricos estruturados — a auditoria visual (Fase 13/14) os consome.
    """
    normal_high  = ref.get("normal_high")
    anomaly_high = ref.get("anomaly_high")
    peak = _peak_point(pts) if pts else None
    dados: dict[str, Any] = {
        "reason":                     reason,
        "observed_value":             round(observed, 1),
        "observed_unit":              "L/h",
        "baseline_metric":            "anomaly_high",
        "baseline_value":             round(anomaly_high, 1) if anomaly_high is not None else None,
        "normal_high":                round(normal_high, 1) if normal_high is not None else None,
        "anomaly_high":               round(anomaly_high, 1) if anomaly_high is not None else None,
        "excess_over_normal":         excess.get("excess_over_normal"),
        "excess_over_normal_pct":     excess.get("excess_over_normal_pct"),
        "excess_over_anomaly":        excess.get("excess_over_anomaly"),
        "excess_over_anomaly_pct":    excess.get("excess_over_anomaly_pct"),
        "baseline_confidence":        ref.get("confidence"),
        "period_type":                period,
        "profile_type":               ref.get("profile_type"),
        "severity_reason":            severity_reason,
        "composite_evidence":         composite_evidence,
        "strong_composite_evidence":  strong_composite_evidence,
        "composite_evidence_factors": composite_evidence_factors,
        "metric_used":                metric,
        "channel_role":               _channel_role(metric),
        "evidence_time":              (
            peak.ts.isoformat() if peak
            else (pts[-1].ts.isoformat() if pts else None)
        ),
        "window_start_at":            pts[0].ts.isoformat() if pts else None,
        "window_end_at":              pts[-1].ts.isoformat() if pts else None,
    }
    if duration_minutes is not None:
        dados["duration_minutes"] = duration_minutes
    if points_confirming is not None:
        dados["points_confirming"] = points_confirming
    return dados


# ── 5. consumo_acima_media (fora da faixa alta — sustentado) ─────────────────
#
# Regra: o valor robusto (p90) da janela de 30 min precisa estar acima de
# normal_high em ≥75% dos pontos (mínimo 3). Um spike isolado não passa.

def detect_consumo_acima_media(ctx: InstallationContext, now: datetime,
                               baseline_ok: bool = True) -> DetectorResult:
    cap = ctx.capabilities
    if cap is None or not (cap.can_alert_flow_outlet or cap.can_alert_flow_inlet):
        return _inactive("consumo_acima_media", "consumo", "not_applicable_no_flow_channel")
    if not baseline_ok:
        return _inactive("consumo_acima_media", "consumo", "baseline_not_ready")

    metric       = consumption_metric(cap)
    channel_role = _channel_role(metric)
    series       = _clean_flow(ctx.series.get(metric, []))

    ref = behavior_ref(ctx, channel_role, metric, "overall")
    if not series or ref is None:
        return _inactive("consumo_acima_media", "consumo", "no_behavior_baseline")

    normal_high  = ref.get("normal_high")
    anomaly_high = ref.get("anomaly_high")
    conf         = ref.get("confidence", "low")
    canal        = _channel_label(metric)

    if normal_high is None or normal_high <= 0 or anomaly_high is None or anomaly_high <= 0:
        return _inactive("consumo_acima_media", "consumo", "incomplete_baseline")

    # Persistência: ≥3 pontos nos últimos 30 min, ≥75% acima de normal_high.
    if not sustained_above(
        series, normal_high,
        min_readings=_SUSTAINED_MIN_POINTS,
        window_minutes=float(_SUSTAINED_WINDOW_MIN),
        coverage_frac=0.75,
        now=now,
    ):
        return _inactive("consumo_acima_media", "consumo", "not_sustained_above_normal")

    # Valor robusto da janela (p90) — não o máximo isolado.
    pts = _window_points(series, _SUSTAINED_WINDOW_MIN, now)
    atual = _robust_high(pts) or 0.0
    if atual < _FLOW_MIN_LPH:
        return _inactive("consumo_acima_media", "consumo", "below_flow_minimum")

    severity, severity_reason = severity_from_band(
        atual, normal_high, anomaly_high, conf,
    )

    result = DetectorResult(rule_key="consumo_acima_media",
                            alert_type="consumo", is_active=False)
    result.current_value = atual

    if severity is None:
        result.reason = severity_reason
        return result

    excess = _excess_fields(atual, normal_high, anomaly_high)
    result.is_active = True
    result.severity  = severity
    result.titulo    = "Consumo acima do padrão desta instalação"
    result.mensagem_usuario = _behavior_message(
        channel_label=canal, observed=atual, unit="L/h",
        normal_high=normal_high, anomaly_high=anomaly_high, excess=excess,
        period_type="overall", baseline_confidence=conf,
        severity=severity, severity_reason=severity_reason,
        composite_factors=[], duration_minutes=float(_SUSTAINED_WINDOW_MIN),
    )
    result.recomendacao = _recommendation_by_severity(severity)
    result.dados_relevantes = _behavior_dados(
        ref, metric, "overall", atual, pts,
        reason="sustained_flow_above_installation_reference",
        severity_reason=severity_reason, excess=excess,
        composite_evidence=False, strong_composite_evidence=False,
        composite_evidence_factors=[],
        duration_minutes=float(_SUSTAINED_WINDOW_MIN),
    )
    return result


# ── 6. consumo_sem_repouso ────────────────────────────────────────────────────

def detect_consumo_sem_repouso(ctx: InstallationContext, now: datetime,
                               baseline_ok: bool = True) -> DetectorResult:
    cap = ctx.capabilities
    if cap is None or not (cap.can_alert_flow_outlet or cap.can_alert_flow_inlet):
        return _inactive("consumo_sem_repouso", "consumo", "not_applicable_no_flow_channel")

    metric       = consumption_metric(cap)
    channel_role = _channel_role(metric)
    series       = _clean_flow(ctx.series.get(metric, []))
    if not series:
        return _inactive("consumo_sem_repouso", "consumo", "no_data")

    ref = behavior_ref(ctx, channel_role, metric, "overall")
    if ref is None:
        return _inactive("consumo_sem_repouso", "consumo", "no_behavior_baseline")

    profile      = ref.get("profile_type")
    conf         = ref.get("confidence", "low")
    normal_high  = ref.get("normal_high")
    anomaly_high = ref.get("anomaly_high")
    canal        = _channel_label(metric)

    if normal_high is None or normal_high <= 0 or anomaly_high is None or anomaly_high <= 0:
        return _inactive("consumo_sem_repouso", "consumo", "incomplete_baseline")

    result = DetectorResult(rule_key="consumo_sem_repouso",
                            alert_type="consumo", is_active=False)
    result.current_value = _last(series)

    # Threshold de "fluxo contínuo anômalo" = normal_high da própria instalação.
    # Perfil contínuo (ex.: Parque Caixa 6–8 L/h) só dispara se a vazão sustentada
    # ficar ACIMA do normal_high — fluxo contínuo dentro do normal não é anomalia.
    flow_threshold = max(normal_high, _FLOW_MIN_LPH)

    # Maior janela em que ≥95% dos pontos ficam acima de normal_high.
    matched_horas: Optional[int] = None
    for horas in (72, 48, 24, 12):
        if _coverage_above_for_hours(series, flow_threshold, horas, now):
            matched_horas = horas
            break

    if matched_horas is None:
        reason = (
            "continuous_flow_profile_normal" if profile == "continuous"
            else "no_sustained_excess"
        )
        result.reason = reason
        return result

    # Vazão média sustentada na janela detectada (observed > normal_high por construção).
    duration_minutes = float(matched_horas * 60)
    pts = _window_points(series, matched_horas * 60, now)
    observed = (sum(p.value for p in pts) / len(pts)) if pts else (_last(series) or 0.0)
    result.current_value = observed

    severity, severity_reason = _severity_from_behavior(
        observed=observed, normal_high=normal_high, anomaly_high=anomaly_high,
        baseline_confidence=conf,
        has_composite_evidence=False, has_strong_composite_evidence=False,
        duration_minutes=duration_minutes,
        detector_key="consumo_sem_repouso", profile_type=profile,
    )
    if severity is None:
        result.reason = severity_reason
        return result

    excess = _excess_fields(observed, normal_high, anomaly_high)
    result.is_active = True
    result.severity  = severity
    result.titulo    = f"Consumo sem pausa acima do padrão nas últimas {matched_horas}h"
    result.mensagem_usuario = _behavior_message(
        channel_label=canal, observed=observed, unit="L/h",
        normal_high=normal_high, anomaly_high=anomaly_high, excess=excess,
        period_type="overall", baseline_confidence=conf,
        severity=severity, severity_reason=severity_reason,
        composite_factors=[], duration_minutes=duration_minutes,
    )
    result.recomendacao = _recommendation_by_severity(severity)
    result.dados_relevantes = _behavior_dados(
        ref, metric, "overall", observed, pts,
        reason="sustained_flow_above_installation_reference",
        severity_reason=severity_reason, excess=excess,
        composite_evidence=False, strong_composite_evidence=False,
        composite_evidence_factors=[],
        duration_minutes=duration_minutes,
    )
    return result


# ── 6b. vazamento_noturno (noites consecutivas sem repouso) ──────────────────
#
# Tática: o consumo noturno que NUNCA cessa por N noites consecutivas indica
# vazamento — uma instalação saudável tem repouso em algum momento da madrugada.
# Usa nights_without_rest de signals.py.

def detect_vazamento_noturno(ctx: InstallationContext, now: datetime,
                             baseline_ok: bool = True) -> DetectorResult:
    cap = ctx.capabilities
    if cap is None or not (cap.can_alert_flow_outlet or cap.can_alert_flow_inlet):
        return _inactive("vazamento_noturno", "consumo", "not_applicable_no_flow_channel")

    metric = consumption_metric(cap)
    # Série curta (72h) — apenas para média/mínima noturna da última madrugada.
    series = _clean_flow(ctx.series.get(metric, []))
    # Série longa (30 dias) — base da contagem de noites sem repouso.
    long = _clean_flow(ctx.long_series.get(metric, [])) or series
    if not series and not long:
        return _inactive("vazamento_noturno", "consumo", "no_data")

    _VAZAMENTO_MIN_DIAS = 2

    result = DetectorResult(rule_key="vazamento_noturno", alert_type="consumo",
                            is_active=False)
    # Média/mínima: sempre da madrugada mais recente (00–06h BRT, últimas 24h).
    flow_mean = _night_flow_mean(series, now)
    flow_min  = _night_flow_min(series, now)
    result.current_value = flow_mean

    # ── Contagem real de noites sem repouso (sobre 30 dias de histórico) ─────
    nights = _nights_without_rest(
        long, rest_threshold=_REST_FLOW_THRESHOLD_LPH,
        min_night_points=3, lookback_days=_LEAK_LOOKBACK_DAYS, now=now,
    )

    prior = ctx.prior_alert_states.get("vazamento_noturno", {})
    prior_dr = prior.get("dados_relevantes", {}) or {}
    prior_active = prior.get("is_active", False)
    prior_first = prior.get("first_triggered_at")

    magnitude_ref_period: str = "overall"

    if nights < _LEAK_LOOKBACK_DAYS:
        # Repouso encontrado dentro da janela: âncora precisa.
        dias_sem_zerar = nights
        anchor = now - timedelta(days=nights)
    else:
        # Janela saturada (vazamento > 30 dias): extender via âncora persistida.
        if prior_active and prior_dr.get("last_rest_at"):
            try:
                anchor = datetime.fromisoformat(
                    prior_dr["last_rest_at"].replace("Z", "+00:00")
                )
            except Exception:
                anchor = now - timedelta(days=_LEAK_LOOKBACK_DAYS)
        elif prior_active and prior_first is not None:
            anchor = prior_first - timedelta(days=_VAZAMENTO_MIN_DIAS)
        else:
            anchor = now - timedelta(days=_LEAK_LOOKBACK_DAYS)
        dias_da_ancora = max(0, int((now - anchor).total_seconds() // 86400))
        dias_sem_zerar = max(nights, dias_da_ancora)

    if dias_sem_zerar < _VAZAMENTO_MIN_DIAS:
        result.reason = f"only_{dias_sem_zerar}_day_without_rest"
        return result

    dias_efetivos = dias_sem_zerar

    # Severidade por tempo
    if dias_efetivos >= 5:
        sev_tempo: Optional[str] = "critico"
    elif dias_efetivos >= 3:
        sev_tempo = "alto"
    else:
        sev_tempo = "moderado"

    # Severidade por magnitude — baseline noturno com fallback overall
    channel_role = _channel_role(metric)
    ref_night = behavior_ref(ctx, channel_role, metric, "night")
    normal_high_ref: Optional[float] = ref_night.get("normal_high") if ref_night else None
    if normal_high_ref and normal_high_ref > 0:
        magnitude_ref_period = "night"
    else:
        ref_overall = behavior_ref(ctx, channel_role, metric, "overall")
        normal_high_ref = ref_overall.get("normal_high") if ref_overall else None
        magnitude_ref_period = "overall"

    sev_mag: Optional[str] = None
    ratio_mag: Optional[float] = None
    if flow_mean is not None and normal_high_ref and normal_high_ref > 0:
        ratio_mag = flow_mean / normal_high_ref
        sev_mag = _severity_from_ratio(ratio_mag, moderado=0.8, alto=1.5, critico=3.0)

    if sev_mag is None:
        severity = "moderado"
    else:
        severity = _max_severity(sev_mag, sev_tempo) or "moderado"

    # Resumo noite-a-noite (prova auditável, primeiras 15 noites).
    nights_summary = _night_by_night_summary(
        long, rest_threshold=_REST_FLOW_THRESHOLD_LPH,
        lookback_days=_LEAK_LOOKBACK_DAYS, now=now,
    )[:15]

    canal = _channel_label(metric)
    result.is_active = True
    result.severity  = severity
    result.titulo    = "Vazão noturna sem repouso — suspeita de vazamento"
    mag_line = (
        f"• Magnitude: {ratio_mag:.1f}× a vazão normal da instalação"
        if ratio_mag is not None else ""
    )
    result.mensagem_usuario = "\n".join(filter(None, [
        f"• Canal: {canal}",
        f"• Vazão não zera há {dias_efetivos} dia(s)",
        (f"• Vazão média noturna: {_fmt(flow_mean)} L/h" if flow_mean else ""),
        (f"• Vazão mínima noturna: {_fmt(flow_min)} L/h" if flow_min else ""),
        mag_line,
        "• Fluxo noturno não cessa — padrão típico de vazamento",
        f"• Classificação: {severity}",
    ]))
    result.recomendacao = _recommendation_by_severity(severity)
    result.dados_relevantes = {
        "reason":               "days_since_last_rest",
        "days_since_last_rest": dias_efetivos,
        "last_rest_at":         anchor.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lookback_days":        _LEAK_LOOKBACK_DAYS,
        "rest_threshold_lph":   _REST_FLOW_THRESHOLD_LPH,
        "nights_summary":       nights_summary,
        "observed_value":       round(flow_mean, 2) if flow_mean else None,
        "observed_unit":        "L/h",
        "night_flow_min":       round(flow_min, 2) if flow_min else None,
        "normal_high_ref":      round(normal_high_ref, 2) if normal_high_ref else None,
        "ratio_magnitude":      round(ratio_mag, 2) if ratio_mag else None,
        "magnitude_ref_period": magnitude_ref_period,
        "metric_used":          metric,
        "channel_role":         channel_role,
        "severity_reason":      f"days_{dias_efetivos}|mag_{sev_mag or 'none'}",
    }
    return result


# ── 6b. vazamento_composto (queda anômala de nível + vazão acima do normal) ─────

def detect_vazamento_composto(ctx: InstallationContext, now: datetime,
                              baseline_ok: bool = True) -> DetectorResult:
    """
    Dispara quando queda acelerada de nível ocorre simultaneamente com vazão
    acima do normal — assinatura clássica de vazamento ativo.

    Requer baseline para ambos os canais. Sem baseline → não dispara.
    """
    cap = ctx.capabilities
    if cap is None or not (cap.can_alert_level and
                           (cap.can_alert_flow_outlet or cap.can_alert_flow_inlet)):
        return _inactive("vazamento_composto", "consumo",
                         "not_applicable_no_level_or_flow")
    if not baseline_ok:
        return _inactive("vazamento_composto", "consumo", "baseline_not_ready")

    level_series = ctx.series.get("level_pct", [])
    metric       = consumption_metric(cap)
    flow_series  = _clean_flow(ctx.series.get(metric, []))

    if len(level_series) < 4 or not flow_series:
        return _inactive("vazamento_composto", "consumo", "insufficient_data")

    drop_pph = _compute_drop_pph_now(level_series, now)
    flow_p90 = _robust_high(_window_pts(flow_series, 60, now))

    if drop_pph is None or flow_p90 is None:
        return _inactive("vazamento_composto", "consumo", "insufficient_data")

    channel_role  = _channel_role(metric)
    level_ref     = behavior_ref(ctx, "tank_level", "level_pct", "overall")
    flow_ref      = behavior_ref(ctx, channel_role, metric, "overall")

    anomaly_drop  = level_ref.get("anomaly_high") if level_ref else None
    normal_high_f = flow_ref.get("normal_high")   if flow_ref  else None

    # Critério 1: queda de nível acima do limite anômalo da instalação
    drop_anomalo = (
        drop_pph >= anomaly_drop if anomaly_drop else drop_pph >= _TANK_FALL_STRONG_LEVEL
    )
    # Critério 2: vazão da saída 20% acima do normal
    flow_anomalo = (
        flow_p90 >= normal_high_f * 1.2 if normal_high_f else flow_p90 >= _FLOW_MIN_LPH
    )

    if not (drop_anomalo and flow_anomalo):
        return _inactive("vazamento_composto", "consumo", "composite_not_met")

    # Severidade: o mais grave entre taxa de queda e excesso de vazão
    sev_drop = (
        "critico" if drop_pph >= 20.0
        else "alto" if drop_pph >= 10.0
        else "moderado"
    )
    ratio_flow: Optional[float] = None
    sev_flow: Optional[str]     = None
    if normal_high_f and normal_high_f > 0:
        ratio_flow = flow_p90 / normal_high_f
        sev_flow   = _severity_from_ratio(ratio_flow, moderado=0.8, alto=1.5, critico=3.0)

    nivel_atual   = _last(level_series) or 0.0
    severity      = _max_severity(sev_drop, sev_flow) or sev_drop
    canal         = _channel_label(metric)

    result = DetectorResult(rule_key="vazamento_composto", alert_type="consumo",
                            is_active=True)
    result.current_value = nivel_atual
    result.severity      = severity
    result.titulo        = "Indício de vazamento — nível caindo com vazão alta"
    result.mensagem_usuario = "\n".join(filter(None, [
        f"• Canal de consumo: {canal}",
        f"• Queda de nível: {_fmt(drop_pph)} p.p./h (anômalo)",
        f"• Nível atual: {_fmt(nivel_atual)}%",
        f"• Vazão de saída: {_fmt(flow_p90)} L/h"
        + (f" ({ratio_flow:.1f}× normal)" if ratio_flow else ""),
        "• Forte indício de vazamento — nível cai enquanto consumo permanece alto",
        f"• Classificação: {severity}",
    ]))
    result.recomendacao   = "Inspecionar pontos de saída e tubulação da instalação."
    result.dados_relevantes = {
        "reason":            "level_drop_with_high_flow",
        "drop_pph":          round(drop_pph, 2),
        "anomaly_drop_ref":  round(anomaly_drop, 2) if anomaly_drop else None,
        "flow_p90_lph":      round(flow_p90, 2),
        "normal_high_ref":   round(normal_high_f, 2) if normal_high_f else None,
        "ratio_flow":        round(ratio_flow, 2) if ratio_flow else None,
        "level_pct_atual":   round(nivel_atual, 1),
        "metric_used":       metric,
        "channel_role":      channel_role,
        "observed_value":    round(nivel_atual, 1),
        "observed_unit":     "%",
        "severity_reason":   f"drop_{sev_drop}|flow_{sev_flow or 'none'}",
    }
    return result


# ── 6c. consumo_ininterrupto (run de fluxo sem repouso por longa janela) ──────
#
# Tática: ≥ X horas de fluxo contínuo sem nenhum período de repouso.
# Para perfis "continuous" (fluxo quase nunca cessa), só dispara se o fluxo
# está ACIMA de normal_high (fluxo contínuo normal não é anomalia).

_CONTINUOUS_ININTERRUPTO_HOURS: dict[str, int] = {
    # (perfil, horas_min) → horas de fluxo ininterrupto para disparar
    "default":    12,   # qualquer instalação: moderado a partir de 12h
}

def detect_consumo_ininterrupto(ctx: InstallationContext, now: datetime,
                                baseline_ok: bool = True) -> DetectorResult:
    cap = ctx.capabilities
    if cap is None or not (cap.can_alert_flow_outlet or cap.can_alert_flow_inlet):
        return _inactive("consumo_ininterrupto", "consumo", "not_applicable_no_flow_channel")

    metric       = consumption_metric(cap)
    channel_role = _channel_role(metric)
    series       = _clean_flow(ctx.series.get(metric, []))
    if not series:
        return _inactive("consumo_ininterrupto", "consumo", "no_data")

    ref     = behavior_ref(ctx, channel_role, metric, "overall")
    profile = ref.get("profile_type") if ref else None

    # Threshold de "fluxo contínuo anômalo":
    # - perfil continuous: acima do normal_high (fluxo normal não é anomalia)
    # - demais: piso técnico de _FLOW_MIN_LPH
    if profile == "continuous" and ref:
        normal_high = ref.get("normal_high") or _FLOW_MIN_LPH
        flow_thr = max(normal_high, _FLOW_MIN_LPH)
    else:
        flow_thr = _FLOW_MIN_LPH

    max_run_min = _max_continuous_flow_min(series, rest_threshold=flow_thr,
                                           lookback_hours=72.0, now=now)
    max_run_h = max_run_min / 60.0

    result = DetectorResult(rule_key="consumo_ininterrupto", alert_type="consumo",
                            is_active=False)
    result.current_value = _last(series)

    thr_moderado = _get_param(ctx.overrides, "consumo_ininterrupto", "thr_moderado", 12.0)
    thr_alto     = _get_param(ctx.overrides, "consumo_ininterrupto", "thr_alto",     24.0)
    thr_critico  = _get_param(ctx.overrides, "consumo_ininterrupto", "thr_critico",  48.0)

    if max_run_h < thr_moderado:
        result.reason = f"max_run_{max_run_h:.1f}h_below_threshold"
        return result

    # Severidade por duração
    if max_run_h >= thr_critico:
        sev_duracao: Optional[str] = "critico"
    elif max_run_h >= thr_alto:
        sev_duracao = "alto"
    else:
        sev_duracao = "moderado"

    # Severidade por magnitude: fluxo mediano do run vs. normal_high
    normal_high_ref = ref.get("normal_high") if ref else None
    flow_median = _robust_high(_window_pts(series, 60, now))
    sev_mag: Optional[str] = None
    ratio_mag: Optional[float] = None
    if flow_median is not None and normal_high_ref and normal_high_ref > 0:
        ratio_mag = flow_median / normal_high_ref
        sev_mag = _severity_from_ratio(ratio_mag, moderado=0.8, alto=1.5, critico=3.0)

    # Magnitude domina: fluxo baixo (ratio < 0.8) → moderado fixo, mesmo persistente.
    # Magnitude relevante combina com duração.
    if sev_mag is None:
        severity = "moderado"
    else:
        severity = _max_severity(sev_mag, sev_duracao) or "moderado"

    canal = _channel_label(metric)
    result.is_active = True
    result.severity  = severity
    result.titulo    = "Consumo ininterrupto — suspeita de vazamento"
    mag_line = (
        f"• Magnitude: {ratio_mag:.1f}× a vazão normal da instalação"
        if ratio_mag is not None else ""
    )
    result.mensagem_usuario = "\n".join(filter(None, [
        f"• Canal: {canal}",
        f"• Duração ininterrupta: {max_run_h:.1f}h",
        f"• Limiar de repouso usado: {_fmt(flow_thr)} L/h",
        (f"• Vazão atual: {_fmt(flow_median)} L/h" if flow_median else ""),
        mag_line,
        (f"• Perfil: {profile}" if profile else ""),
        f"• Classificação: {severity}",
    ]))
    result.recomendacao = _recommendation_by_severity(severity)
    result.dados_relevantes = {
        "reason":              "continuous_flow_no_rest",
        "max_run_hours":       round(max_run_h, 2),
        "flow_threshold_lph":  round(flow_thr, 2),
        "flow_median_lph":     round(flow_median, 2) if flow_median else None,
        "normal_high_ref":     round(normal_high_ref, 2) if normal_high_ref else None,
        "ratio_magnitude":     round(ratio_mag, 2) if ratio_mag else None,
        "profile_type":        profile,
        "metric_used":         metric,
        "channel_role":        channel_role,
        "severity_reason":     f"run_{max_run_h:.0f}h|mag_{sev_mag or 'none'}",
    }
    return result


# ── 7. vazao_noturna ──────────────────────────────────────────────────────────

def detect_vazao_noturna(ctx: InstallationContext, now: datetime,
                         baseline_ok: bool = True) -> DetectorResult:
    cap = ctx.capabilities
    if cap is None or not (cap.can_alert_flow_outlet or cap.can_alert_flow_inlet):
        return _inactive("vazao_noturna", "consumo", "not_applicable_no_flow_channel")

    metric       = consumption_metric(cap)
    channel_role = _channel_role(metric)
    series       = _clean_flow(ctx.series.get(metric, []))

    # Referência noturna: usa o período "night" da própria instalação.
    ref = behavior_ref(ctx, channel_role, metric, "night")
    if not series or ref is None:
        return _inactive("vazao_noturna", "consumo", "no_behavior_baseline")

    night_mean = _night_flow_mean(series, now)
    if night_mean is None or night_mean < _FLOW_MIN_LPH:
        return _inactive("vazao_noturna", "consumo", "no_night_flow")

    normal_high  = ref.get("normal_high")
    anomaly_high = ref.get("anomaly_high")
    conf         = ref.get("confidence", "low")
    canal        = _channel_label(metric)

    if normal_high is None or normal_high <= 0 or anomaly_high is None or anomaly_high <= 0:
        return _inactive("vazao_noturna", "consumo", "incomplete_baseline")

    # Evidência composta (saída da caixa): queda noturna de nível/pressão reforça suspeita.
    if metric == "flow2_lph":
        has_comp, has_strong, factors = _tank_fall_evidence(ctx, now)
    else:
        has_comp, has_strong, factors = False, False, []

    severity, severity_reason = _severity_from_behavior(
        observed=night_mean, normal_high=normal_high, anomaly_high=anomaly_high,
        baseline_confidence=conf,
        has_composite_evidence=has_comp,
        has_strong_composite_evidence=has_strong,
        duration_minutes=None,
        detector_key="vazao_noturna", profile_type=ref.get("profile_type"),
    )

    result = DetectorResult(rule_key="vazao_noturna",
                            alert_type="consumo", is_active=False)
    result.current_value = night_mean

    if severity is None:
        result.reason = severity_reason
        return result

    excess = _excess_fields(night_mean, normal_high, anomaly_high)
    result.is_active = True
    result.severity  = severity
    result.titulo    = (
        "Consumo noturno acima do padrão — suspeita de vazamento"
        if night_mean > anomaly_high
        else "Consumo noturno acima do esperado para esta instalação"
    )
    result.mensagem_usuario = _behavior_message(
        channel_label=canal, observed=night_mean, unit="L/h",
        normal_high=normal_high, anomaly_high=anomaly_high, excess=excess,
        period_type="night", baseline_confidence=conf,
        severity=severity, severity_reason=severity_reason,
        composite_factors=factors, duration_minutes=None,
    )
    result.recomendacao = _recommendation_by_severity(severity)
    result.dados_relevantes = _behavior_dados(
        ref, metric, "night", night_mean, series[-1:],
        reason="night_flow_elevated",
        severity_reason=severity_reason, excess=excess,
        composite_evidence=has_comp, strong_composite_evidence=has_strong,
        composite_evidence_factors=factors,
    )
    return result


# ── 8. pico_consumo (rebaixado — janela sustentada, teto = moderado) ──────────

def detect_pico_consumo(ctx: InstallationContext, now: datetime,
                        baseline_ok: bool = True) -> DetectorResult:
    cap = ctx.capabilities
    if cap is None or not (cap.can_alert_flow_outlet or cap.can_alert_flow_inlet):
        return _inactive("pico_consumo", "consumo", "not_applicable_no_flow_channel")

    metric       = consumption_metric(cap)
    channel_role = _channel_role(metric)
    series       = _clean_flow(ctx.series.get(metric, []))

    ref = behavior_ref(ctx, channel_role, metric, "overall")
    if not series or ref is None:
        return _inactive("pico_consumo", "consumo", "no_behavior_baseline")

    # Janela de 30 min com valor robusto (p90), não o ponto máximo isolado.
    # Persistência exigida: ≥3 pontos, ≥75% da janela sustentados acima de normal_high.
    normal_high  = ref.get("normal_high")
    anomaly_high = ref.get("anomaly_high")
    conf         = ref.get("confidence", "low")
    canal        = _channel_label(metric)

    if normal_high is None or normal_high <= 0 or anomaly_high is None or anomaly_high <= 0:
        return _inactive("pico_consumo", "consumo", "incomplete_baseline")

    if not sustained_above(
        series, normal_high,
        min_readings=_TANK_MIN_READINGS,
        window_minutes=30.0,
        coverage_frac=0.75,
        now=now,
    ):
        return _inactive("pico_consumo", "consumo", "not_sustained_above_normal")

    pts = _window_points(series, 30, now)
    # Valor robusto: p90 da janela. Filtra spikes isolados que inflariam o máximo.
    atual = _robust_high(pts) or 0.0
    if atual < _FLOW_MIN_LPH:
        return _inactive("pico_consumo", "consumo", "below_flow_minimum")

    severity, severity_reason = severity_from_band(
        atual, normal_high, anomaly_high, conf,
    )

    result = DetectorResult(rule_key="pico_consumo",
                            alert_type="consumo", is_active=False)
    result.current_value = atual

    if severity is None:
        result.reason = severity_reason
        return result

    excess = _excess_fields(atual, normal_high, anomaly_high)
    result.is_active = True
    result.severity  = severity
    result.titulo    = "Pico de consumo acima do padrão desta instalação"
    result.mensagem_usuario = _behavior_message(
        channel_label=canal, observed=atual, unit="L/h",
        normal_high=normal_high, anomaly_high=anomaly_high, excess=excess,
        period_type="overall", baseline_confidence=conf,
        severity=severity, severity_reason=severity_reason,
        composite_factors=[], duration_minutes=30.0,
    )
    result.recomendacao = _recommendation_by_severity(severity)
    result.dados_relevantes = _behavior_dados(
        ref, metric, "overall", atual, pts,
        reason="flow_peak_sustained_window",
        severity_reason=severity_reason, excess=excess,
        composite_evidence=False, strong_composite_evidence=False,
        composite_evidence_factors=[],
        duration_minutes=30.0,
    )
    return result


# ── 7b. consumo_baixo (perfil continuous: consumo anormalmente baixo) ─────────

def detect_consumo_baixo(ctx: InstallationContext, now: datetime,
                         baseline_ok: bool = True) -> DetectorResult:
    """
    Consumo anormalmente BAIXO — só faz sentido físico em perfil `continuous`
    (fluxo que normalmente nunca cessa; queda abaixo do limite inferior sugere
    interrupção). Perfis intermittent/inactive zeram no dia a dia → não alertam.
    A severidade escala com a intensidade abaixo do limite (mais perto de zero,
    mais grave).
    """
    cap = ctx.capabilities
    if cap is None or not (cap.can_alert_flow_outlet or cap.can_alert_flow_inlet):
        return _inactive("consumo_baixo", "consumo", "not_applicable_no_flow_channel")
    if not baseline_ok:
        return _inactive("consumo_baixo", "consumo", "baseline_not_ready")

    metric       = consumption_metric(cap)
    channel_role = _channel_role(metric)
    series       = _clean_flow(ctx.series.get(metric, []))

    ref = behavior_ref(ctx, channel_role, metric, "overall")
    if not series or ref is None:
        return _inactive("consumo_baixo", "consumo", "no_behavior_baseline")

    if ref.get("profile_type") != "continuous":
        return _inactive("consumo_baixo", "consumo", "profile_not_continuous")

    normal_low  = ref.get("normal_low")
    anomaly_low = ref.get("anomaly_low")
    conf        = ref.get("confidence", "low")
    canal       = _channel_label(metric)

    # anomaly_low só é fisicamente útil quando positivo.
    if anomaly_low is None or anomaly_low <= 0:
        return _inactive("consumo_baixo", "consumo", "incomplete_baseline")

    # Persistência exigida: ≥3 pontos, ≥75% da janela abaixo de normal_low.
    if not sustained_below(
        series, normal_low or anomaly_low,
        min_readings=_SUSTAINED_MIN_POINTS,
        window_minutes=float(_SUSTAINED_WINDOW_MIN),
        coverage_frac=0.75,
        now=now,
    ):
        return _inactive("consumo_baixo", "consumo", "not_sustained_below_normal")

    pts  = _window_points(series, _SUSTAINED_WINDOW_MIN, now)
    atual = sum(p.value for p in pts) / len(pts) if pts else 0.0

    severity, severity_reason = severity_from_band_low(
        atual, normal_low, anomaly_low, conf,
    )

    result = DetectorResult(rule_key="consumo_baixo", alert_type="consumo",
                            is_active=False)
    result.current_value = atual

    if severity is None:
        result.reason = severity_reason
        return result

    deficit = round((anomaly_low - atual) if atual < anomaly_low else 0.0, 1)
    lines = [
        f"• Canal: {canal}",
        f"• Valor observado: {_fmt(atual)} L/h",
        f"• Mínimo normal: {_fmt(normal_low)} L/h",
        f"• Limite inferior de anomalia: abaixo de {_fmt(anomaly_low)} L/h",
        f"• Déficit: {_fmt(deficit)} L/h",
        "• Perfil: fluxo contínuo (consumo não deveria cessar)",
        f"• Confiança da baseline: {conf}",
        f"• Classificação: {severity} — {severity_reason.split('|')[0]}",
    ]

    result.is_active        = True
    result.severity         = severity
    result.titulo           = "Consumo anormalmente baixo (fluxo contínuo)"
    result.mensagem_usuario = "\n".join(lines)
    result.recomendacao     = _recommendation_by_severity(severity)
    result.dados_relevantes = {
        "reason":                "flow_below_normal_low_continuous",
        "observed_value":        round(atual, 2),
        "observed_unit":         "L/h",
        "normal_low":            round(normal_low, 2) if normal_low is not None else None,
        "anomaly_low":           round(anomaly_low, 2),
        "deficit_below_anomaly": deficit,
        "profile_type":          "continuous",
        "confidence":            conf,
        "severity_reason":       severity_reason,
        "metric_used":           metric,
        "channel_role":          channel_role,
        "window_start_at":       pts[0].ts.isoformat() if pts else None,
        "window_end_at":         pts[-1].ts.isoformat() if pts else None,
        "duration_minutes":      float(_SUSTAINED_WINDOW_MIN),
    }
    return result


# ── 7c. variacao_rapida (velocidade recente vs. típica da instalação) ─────────

# Canais elegíveis ao detector de velocidade: (metric, channel_role, label, unit).
# A vazão (consumo) é resolvida dinamicamente por consumption_metric.
_VELOCITY_NON_FLOW_CHANNELS: tuple[tuple[str, str, str, str], ...] = (
    ("pressure",  "street_pressure", "pressão da rua",   "mca"),
    ("pressure2", "tank_pressure",   "pressão da caixa", "mca"),
    ("level_pct", "tank_level",      "nível da caixa",   "%"),
)

# Tipo do alerta de variacao_rapida conforme a métrica vencedora.
_VELOCITY_ALERT_TYPE: dict[str, str] = {
    "flow1_lph": "consumo", "flow2_lph": "consumo",
    "pressure": "pressao", "pressure2": "pressao",
    "level_pct": "nivel",
}


def detect_variacao_rapida(ctx: InstallationContext, now: datetime,
                           baseline_ok: bool = True) -> DetectorResult:
    """
    Variação ANORMALMENTE RÁPIDA de uma métrica vs. a velocidade típica daquela
    instalação (`typical_variation_per_hour`). Captura a *dinâmica* (taxa), não
    a magnitude — pega picos e fundos curtos mesmo quando a magnitude é
    suavizada. Cobre subida e queda, em vazão, pressão e nível.

    A severidade escala com o múltiplo (velocidade recente / típica). Avalia
    todos os canais aplicáveis e reporta o mais severo (rule_key único).
    """
    cap = ctx.capabilities
    if cap is None:
        return _inactive("variacao_rapida", "consumo", "not_applicable_no_capabilities")
    if not baseline_ok:
        return _inactive("variacao_rapida", "consumo", "baseline_not_ready")

    # Monta os canais candidatos conforme as capacidades inferidas.
    candidates: list[tuple[str, str, str, str]] = []
    if cap.can_alert_flow_outlet or cap.can_alert_flow_inlet:
        fm = consumption_metric(cap)
        if fm is not None:
            candidates.append((fm, _channel_role(fm), _channel_label(fm), "L/h"))
    if cap.can_alert_street_pressure:
        candidates.append(_VELOCITY_NON_FLOW_CHANNELS[0])
    if cap.has_tank_pressure:
        candidates.append(_VELOCITY_NON_FLOW_CHANNELS[1])
    if cap.can_alert_level:
        candidates.append(_VELOCITY_NON_FLOW_CHANNELS[2])

    if not candidates:
        return _inactive("variacao_rapida", "consumo", "no_applicable_channel")

    best: Optional[dict[str, Any]] = None
    for metric, channel_role, label, unit in candidates:
        series = ctx.series.get(metric, [])
        if metric in ("flow1_lph", "flow2_lph"):
            series = _clean_flow(series)
        ref = behavior_ref(ctx, channel_role, metric, "overall")
        if not series or ref is None:
            continue

        vt = ref.get("typical_variation_per_hour")
        if vt is None or vt <= 0:
            continue

        pts = _window_points(series, _VELOCITY_WINDOW_MIN, now)
        if len(pts) < _VELOCITY_MIN_POINTS:
            continue

        vel_recent = typical_variation_per_hour(
            [p.value for p in pts], [p.ts for p in pts]
        )
        if vel_recent is None or vel_recent <= 0:
            continue

        # Guarda anti-ruído: o movimento absoluto recente precisa ser relevante
        # frente à faixa normal do canal — evita jitter em sinais quase-constantes.
        nl = ref.get("normal_low")
        nh = ref.get("normal_high")
        scale = (nh - nl) if (nh is not None and nl is not None and nh > nl) else None
        delta_abs = max(p.value for p in pts) - min(p.value for p in pts)
        if scale is not None and delta_abs < _VELOCITY_MIN_DELTA_FRAC * scale:
            continue

        mult = vel_recent / vt
        if mult < _VELOCITY_TRIGGER_MULT:
            continue

        conf = ref.get("confidence", "low")
        severity, severity_reason = _severity_from_multiple(
            mult, conf,
            t_moderado=_VELOCITY_MODERADO_MULT,
            t_alto=_VELOCITY_ALTO_MULT,
            t_critico=_VELOCITY_CRITICO_MULT,
            reason_prefix="velocity",
        )
        direction = "alta" if pts[-1].value >= pts[0].value else "queda"
        cand = {
            "metric": metric, "channel_role": channel_role, "label": label,
            "unit": unit, "severity": severity, "severity_reason": severity_reason,
            "mult": mult, "vel_recent": vel_recent, "vt": vt,
            "direction": direction, "conf": conf, "pts": pts,
        }
        if best is None or (
            _SEV_ORDER[severity] > _SEV_ORDER[best["severity"]]
            or (_SEV_ORDER[severity] == _SEV_ORDER[best["severity"]]
                and mult > best["mult"])
        ):
            best = cand

    if best is None:
        return _inactive("variacao_rapida", "consumo", "no_rapid_variation")

    pts        = best["pts"]
    unit       = best["unit"]
    label      = best["label"]
    severity   = best["severity"]
    mult       = best["mult"]
    sentido    = "subida" if best["direction"] == "alta" else "queda"
    atual      = pts[-1].value

    lines = [
        f"• Canal: {label}",
        f"• Variação recente: {_fmt(best['vel_recent'])} {unit}/h "
        f"(típico: {_fmt(best['vt'])} {unit}/h)",
        f"• Velocidade {_fmt(mult)}× acima do normal desta instalação",
        f"• Sentido: {sentido} rápida",
        f"• Valor atual: {_fmt(atual)} {unit}",
        f"• Confiança da baseline: {best['conf']}",
        f"• Classificação: {severity} — variação muito rápida",
    ]

    result = DetectorResult(rule_key="variacao_rapida",
                            alert_type=_VELOCITY_ALERT_TYPE.get(best["metric"], "consumo"),
                            is_active=True)
    result.current_value    = atual
    result.severity         = severity
    result.titulo           = f"Variação muito rápida — {label}"
    result.mensagem_usuario = "\n".join(lines)
    result.recomendacao     = _recommendation_by_severity(severity)
    result.dados_relevantes = {
        "reason":                     "velocity_above_typical",
        "metric_used":                best["metric"],
        "channel_role":               best["channel_role"],
        "observed_unit":              unit,
        "current_value":              round(atual, 1),
        "recent_variation_per_hour":  round(best["vel_recent"], 2),
        "typical_variation_per_hour": round(best["vt"], 2),
        "velocity_multiple":          round(mult, 1),
        "direction":                  best["direction"],
        "baseline_confidence":        best["conf"],
        "severity_reason":            best["severity_reason"],
        "evidence_time":              pts[-1].ts.isoformat(),
        "window_start_at":            pts[0].ts.isoformat(),
        "window_end_at":              pts[-1].ts.isoformat(),
    }
    return result


# ── 8b. sensor_pressao_rua_falha (pressure≈0 mas temperature>0 — sensor pifou) ──

def detect_sensor_pressao_rua_falha(ctx: InstallationContext, now: datetime) -> DetectorResult:
    cap = ctx.capabilities
    if cap is None or not cap.can_alert_street_pressure:
        return _inactive("sensor_pressao_rua_falha", "sensor",
                         "not_applicable_without_street_pressure")

    pressure = ctx.series.get("pressure", [])
    temperature = ctx.series.get("temperature", [])
    if not pressure or not temperature:
        return _inactive("sensor_pressao_rua_falha", "sensor", "no_series")

    p_zero = sustained_below(pressure, _TANK_ZERO_TOL,
                             min_readings=3, window_minutes=30.0, coverage_frac=0.75, now=now)
    t_ok = sustained_above(temperature, _TANK_ZERO_TOL,
                           min_readings=3, window_minutes=30.0, coverage_frac=0.75, now=now)
    if not (p_zero and t_ok):
        return _inactive("sensor_pressao_rua_falha", "sensor", "condition_not_met")

    pts_p = _window_points(pressure, 30, now)
    last_p = pts_p[-1].value if pts_p else 0.0
    last_ts = pts_p[-1].ts if pts_p else now

    result = DetectorResult(rule_key="sensor_pressao_rua_falha",
                            alert_type="sensor", is_active=True)
    result.severity = "alto"
    result.current_value = last_p
    result.titulo = "Sensor de pressão da rua sem leitura"
    result.mensagem_usuario = (
        "A remota continua enviando dados, mas a pressão da rua está em zero "
        "há ≥30 min. Provável defeito no sensor de pressão da rua (cabo, "
        "manômetro, alimentação do canal)."
    )
    result.recomendacao = "Inspecionar o sensor/cabo de pressão da rua."
    result.dados_relevantes = {
        "reason":              "pressure_zero_temperature_valid",
        "evidence_time":       last_ts.isoformat(),
        "pressure_mca":        round(last_p, 2),
        "capability_confidence": cap.confidence,
    }
    return result


# ── 8b2. remota_sem_leitura (pressure≈0 ∧ temperature≈0 — remota deu pau) ──────

def detect_remota_sem_leitura(ctx: InstallationContext, now: datetime) -> DetectorResult:
    cap = ctx.capabilities
    if cap is None or not (cap.has_pressure1 or cap.has_temperature1):
        return _inactive("remota_sem_leitura", "sensor",
                         "not_applicable_no_street_channel")

    pressure = ctx.series.get("pressure", [])
    temperature = ctx.series.get("temperature", [])
    if not pressure or not temperature:
        return _inactive("remota_sem_leitura", "sensor", "no_series")

    p_zero = sustained_below(pressure, _TANK_ZERO_TOL,
                             min_readings=3, window_minutes=30.0, coverage_frac=0.75, now=now)
    t_zero = sustained_below(temperature, _TANK_ZERO_TOL,
                             min_readings=3, window_minutes=30.0, coverage_frac=0.75, now=now)
    if not (p_zero and t_zero):
        return _inactive("remota_sem_leitura", "sensor", "condition_not_met")

    pts_p = _window_points(pressure, 30, now)
    last_p = pts_p[-1].value if pts_p else 0.0
    last_ts = pts_p[-1].ts if pts_p else now

    result = DetectorResult(rule_key="remota_sem_leitura",
                            alert_type="sensor", is_active=True)
    result.severity = "critico"
    result.current_value = last_p
    result.titulo = "Remota sem leitura"
    result.mensagem_usuario = (
        "Pressão e temperatura da rua zeradas há ≥30 min. Possível falha de "
        "hardware, conexão ou alimentação da remota."
    )
    result.recomendacao = "Verificar alimentação, antena/sinal LoRa e estado físico da remota."
    result.dados_relevantes = {
        "reason":              "pressure_zero_temperature_zero",
        "evidence_time":       last_ts.isoformat(),
        "pressure_mca":        round(last_p, 2),
        "capability_confidence": cap.confidence,
    }
    return result


# ── 8c. caixa_sem_pressao (hidráulico — p2≈0 ∧ t2>0) ──────────────────────────

def detect_caixa_sem_pressao(ctx: InstallationContext, now: datetime) -> DetectorResult:
    cap = ctx.capabilities
    if cap is None or not cap.can_alert_tank:
        return _inactive("caixa_sem_pressao", "nivel",
                         "not_applicable_without_tank_pressure")

    p2 = ctx.series.get("pressure2", [])
    t2 = ctx.series.get("temperature2", [])
    p2v = _last_n(p2, _TANK_MIN_READINGS)
    t2v = _last_n(t2, _TANK_MIN_READINGS)
    if len(p2v) < _TANK_MIN_READINGS or len(t2v) < _TANK_MIN_READINGS:
        return _inactive("caixa_sem_pressao", "nivel", "insufficient_readings")

    p2_zero = all(abs(v) <= _TANK_ZERO_TOL for v in p2v)
    t2_ok = all(v > _TANK_ZERO_TOL for v in t2v)   # temperatura respondendo
    if not (p2_zero and t2_ok):
        return _inactive("caixa_sem_pressao", "nivel", "condition_not_met")

    last_ts = p2[-1].ts if p2 else now
    result = DetectorResult(rule_key="caixa_sem_pressao",
                            alert_type="nivel", is_active=True)
    result.severity = "alto"
    result.current_value = p2v[-1]
    result.titulo = "Caixa d'água sem pressão"
    result.mensagem_usuario = (
        "A pressão da caixa está zerada, mas o sensor continua respondendo "
        "temperatura. Isso indica possível falta de água na caixa."
    )
    result.recomendacao = "Verificar abastecimento e nível da caixa d'água."
    result.dados_relevantes = {
        # reason-code físico — independente de baseline (Fase 8).
        "reason":            "pressure2_zero_temperature2_valid",
        "points_confirming":  len(p2v),
        "evidence_time":     last_ts.isoformat(),
        "pressure2":         round(p2v[-1], 2),
        "temperature2":      round(t2v[-1], 2),
        "capability_confidence": cap.confidence,
        "has_tank_pressure": True,
    }
    return result


# ── 8d. pressao_rua_baixa (pisos absolutos configuráveis) ─────────────────────

def detect_pressao_rua_baixa(ctx: InstallationContext, now: datetime) -> DetectorResult:
    cap = ctx.capabilities
    if cap is None or not cap.can_alert_street_pressure:
        return _inactive("pressao_rua_baixa", "pressao",
                         "not_applicable_without_street_pressure")

    series = ctx.series.get("pressure", [])
    if not series:
        return _inactive("pressao_rua_baixa", "pressao", "no_series")

    pts = _window_points(series, 60, now)
    if len(pts) < _SUSTAINED_MIN_POINTS:
        return _inactive("pressao_rua_baixa", "pressao", "insufficient_points")

    # Mediana da janela de 60 min — resistente a outlier
    values = sorted(p.value for p in pts)
    atual = values[len(values) // 2]

    s = ctx.settings or get_settings()
    floor_mod   = s.street_pressure_moderado_mca  # 15.0 MCA
    floor_alto  = s.street_pressure_alto_mca      # 10.0 MCA
    floor_crit  = s.street_pressure_critico_mca   # 5.0 MCA

    if atual >= floor_mod:
        return _inactive("pressao_rua_baixa", "pressao", "above_floor")

    if atual < floor_crit:
        severity = "critico"
    elif atual < floor_alto:
        severity = "alto"
    else:
        severity = "moderado"

    severity = _min_severity_new(severity, _severity_cap_by_confidence(cap.confidence))  # confidence cap

    baseline = ctx.baselines.get("pressure") or {}
    p10: Optional[float] = baseline.get("p10")

    result = DetectorResult(rule_key="pressao_rua_baixa",
                            alert_type="pressao", is_active=True)
    result.severity = severity
    result.current_value = atual
    result.titulo = "Pressão da rua baixa"
    ref = f" (usual ~{p10:.1f} MCA)" if p10 else ""
    result.mensagem_usuario = (
        f"Pressão da rua sustentada em {atual:.1f} MCA na última hora{ref}."
    )
    result.recomendacao = "Verificar abastecimento da concessionária / pressão da rede."
    result.dados_relevantes = {
        "evidence_time":        pts[-1].ts.isoformat(),
        "window_start_at":      pts[0].ts.isoformat(),
        "window_end_at":        pts[-1].ts.isoformat(),
        "metric_used":          "pressure",
        "channel_role":         "street",
        "pressure_atual_mca":   round(atual, 1),
        "ref_p10_mca":          round(p10, 1) if p10 else None,
        "floor_attention_mca":  floor_aten,
        "floor_alto_mca":       floor_alto,
        "floor_critico_mca":    floor_crit,
        "capability_confidence": cap.confidence,
    }
    return result


# ── 8e. vazamento_pos_caixa (composto — saída contínua + caixa caindo) ────────

def detect_vazamento_pos_caixa(ctx: InstallationContext, now: datetime,
                               baseline_ok: bool = True) -> DetectorResult:
    cap = ctx.capabilities
    if cap is None or not (cap.can_alert_flow_outlet and cap.has_tank_pressure):
        return _inactive("vazamento_pos_caixa", "consumo",
                         "not_applicable_without_tank_outlet")

    series = _clean_flow(ctx.series.get("flow2_lph", []))
    ref = behavior_ref(ctx, "tank_outlet", "flow2_lph", "overall")
    if not series or ref is None:
        return _inactive("vazamento_pos_caixa", "consumo", "no_behavior_baseline")

    normal_high  = ref.get("normal_high")
    anomaly_high = ref.get("anomaly_high")
    conf         = ref.get("confidence", "low")
    canal        = _channel_label("flow2_lph")

    if normal_high is None or normal_high <= 0 or anomaly_high is None or anomaly_high <= 0:
        return _inactive("vazamento_pos_caixa", "consumo", "incomplete_baseline")

    # Passo 1: fluxo de saída contínuo acima do normal desta instalação por ≥2h.
    continuo_threshold = max(normal_high, _FLOW_MIN_LPH)
    continuo = _coverage_above_for_hours(
        series, continuo_threshold, 2.0, now, min_coverage=0.9
    )
    if not continuo:
        return _inactive("vazamento_pos_caixa", "consumo", "not_continuous")

    # Passo 2: evidência composta (queda de nível/pressão) em dois níveis.
    # Queda LEVE basta para disparar; só queda FORTE/persistente (ou 2x anomalia)
    # eleva a severidade a crítico — queda leve isolada NÃO gera crítico.
    has_comp, has_strong, factors = _tank_fall_evidence(ctx, now)
    if not has_comp:
        return _inactive("vazamento_pos_caixa", "consumo", "tank_not_falling")

    pts   = _window_points(series, 120, now)
    atual = (sum(p.value for p in pts) / len(pts)) if pts else 0.0

    # Severidade 100% via regra central (sem piso artificial):
    #   faixa + queda leve  → moderado;  faixa + queda forte → alto;
    #   > anomaly (+queda)   → alto;      >= 2x anomaly OU queda forte → critico;
    #   confidence=low       → teto moderado.
    severity, severity_reason = _severity_from_behavior(
        observed=atual, normal_high=normal_high, anomaly_high=anomaly_high,
        baseline_confidence=conf,
        has_composite_evidence=has_comp,
        has_strong_composite_evidence=has_strong,
        duration_minutes=120.0,
        detector_key="vazamento_pos_caixa", profile_type=ref.get("profile_type"),
    )
    if severity is None:
        # observed <= normal_high: apesar da continuidade, está no padrão normal.
        return _inactive("vazamento_pos_caixa", "consumo", severity_reason)

    excess = _excess_fields(atual, normal_high, anomaly_high)
    result = DetectorResult(rule_key="vazamento_pos_caixa",
                            alert_type="consumo", is_active=True)
    result.severity      = severity
    result.current_value = atual
    result.titulo        = "Possível vazamento após a caixa d'água"
    result.mensagem_usuario = _behavior_message(
        channel_label=canal, observed=atual, unit="L/h",
        normal_high=normal_high, anomaly_high=anomaly_high, excess=excess,
        period_type="overall", baseline_confidence=conf,
        severity=severity, severity_reason=severity_reason,
        composite_factors=factors, duration_minutes=120.0,
    )
    result.recomendacao = _recommendation_by_severity(severity)
    result.dados_relevantes = _behavior_dados(
        ref, "flow2_lph", "overall", atual, pts,
        reason="outlet_continuous_tank_falling",
        severity_reason=severity_reason, excess=excess,
        composite_evidence=has_comp, strong_composite_evidence=has_strong,
        composite_evidence_factors=factors,
        duration_minutes=120.0,
    )
    result.dados_relevantes["tank_falling"] = True
    return result


# ── 9. queda_nivel — helpers comportamentais ──────────────────────────────────

# Constantes do safety fallback (sem baseline tank_level disponível).
_SAFETY_DROP_PPH_MIN: float = 30.0   # queda extrema — ~3× o típico
_SAFETY_LEVEL_MAX: float = 50.0      # nível já em risco

# Piso de nível considerado "operacionalmente seguro" para queda_nivel.
# Abaixo desse limiar a severidade sobe para "alto" mesmo sem evidência composta.
_LEVEL_PCT_SAFE_FLOOR: float = 60.0

# Prioridade de período para queda_nivel (prédio público: noite > fim de semana).
_LEVEL_PERIOD_PRIORITY: tuple[str, ...] = (
    "night", "weekend", "business_hours", "off_hours", "day", "overall"
)


def _current_period_type(now: datetime) -> str:
    """Período de maior prioridade para o instante now (em BRT)."""
    periods = period_types_for(to_brt(now))
    for p in _LEVEL_PERIOD_PRIORITY:
        if p in periods:
            return p
    return "overall"


def _cap_queda_nivel_alto(
    severity: Optional[str], reason: str
) -> tuple[Optional[str], str]:
    """queda_nivel nunca passa de 'alto' — crítico é responsabilidade de nivel_baixo.

    Nota: o detector primário usa _severity_queda_nivel (que já não retorna 'critico').
    Esta função é mantida como defesa em profundidade.
    """
    if severity == "critico":
        return "alto", reason + "|capped_below_critico_use_nivel_baixo"
    return severity, reason


def _severity_queda_nivel(
    *,
    observed: float,
    normal_high: Optional[float],
    anomaly_high: Optional[float],
    baseline_confidence: str,
    level_pct_atual: Optional[float],
    has_composite_evidence: bool = False,
    has_strong_composite_evidence: bool = False,
) -> tuple[Optional[str], str]:
    """
    Regra de severidade específica para queda_nivel.

    Diferente da regra genérica (_severity_from_behavior), considera o nível
    atual do reservatório: uma queda acima do anômalo com nível ainda em faixa
    segura (>= _LEVEL_PCT_SAFE_FLOOR) é 'moderado', não 'alto'. Isso evita
    alarme desnecessário quando a velocidade de queda é anômala mas o tanque
    ainda está operacional.

    Nunca retorna 'critico' — papel exclusivo de nivel_baixo / autonomia_insuficiente.
    """
    if normal_high is None or anomaly_high is None:
        return None, "incomplete_baseline"
    if observed <= normal_high:
        return None, "within_normal_profile"
    if observed <= anomaly_high:
        # Dentro da banda: não dispara (sem "atencao").
        return None, "band_below_anomaly"

    # Acima do limite anômalo — determinar severidade pelo contexto.
    if has_strong_composite_evidence:
        raw, reason = "alto", "strong_composite_evidence"
    elif observed >= 2.0 * anomaly_high:
        raw, reason = "alto", "at_least_2x_anomaly"
    elif level_pct_atual is not None and level_pct_atual < _LEVEL_PCT_SAFE_FLOOR:
        raw, reason = "alto", "above_anomaly_low_tank_level"
    else:
        # Nível ainda seguro e sem evidência composta forte → moderado.
        raw, reason = "moderado", "above_anomaly_safe_tank_level"

    # Teto por confiança da baseline (low→moderado, medium→alto, high/consolidated→alto).
    cap = _min_severity(raw, severity_cap_by_confidence(baseline_confidence))
    if cap != raw:
        reason += f"|capped_{baseline_confidence}"
    # Garantia adicional: nunca 'critico'.
    cap, reason = _cap_queda_nivel_alto(cap, reason)
    return cap, reason


def _queda_nivel_message(
    *,
    nivel_atual: float,
    observed: float,
    unit: str,
    normal_high: Optional[float],
    anomaly_high: Optional[float],
    excess: dict[str, Optional[float]],
    period_type: str,
    baseline_confidence: str,
    severity: str,
    severity_reason: str,
    composite_factors: list[str],
    duration_minutes: Optional[float],
) -> str:
    """
    Monta mensagem_usuario específica para queda_nivel.

    Comunica explicitamente que o alerta é sobre velocidade de queda,
    não sobre nível atual baixo — evitando interpretação errada quando
    o nível ainda está em faixa operacional segura.
    """
    lines: list[str] = []
    tank_status = (
        "faixa operacional segura"
        if nivel_atual >= _LEVEL_PCT_SAFE_FLOOR
        else "nível baixo — verificar imediatamente"
    )
    lines.append(
        "• Tipo: queda acelerada do nível do reservatório "
        "(este alerta é sobre velocidade de queda, não sobre nível baixo)"
    )
    lines.append(f"• Nível atual: {_fmt(nivel_atual)}%  ({tank_status})")
    lines.append(f"• Taxa de queda observada: {_fmt(observed)} {unit}")
    if normal_high is not None:
        lines.append(
            f"• Padrão normal da instalação ({period_type}): até {_fmt(normal_high)} {unit}"
        )
    if anomaly_high is not None:
        lines.append(
            f"• Limite anômalo da instalação ({period_type}): acima de {_fmt(anomaly_high)} {unit}"
        )
    eoa = excess.get("excess_over_anomaly")
    eoa_pct = excess.get("excess_over_anomaly_pct")
    if eoa is not None and eoa > 0:
        pct_str = f" (+{_fmt_pct(eoa_pct)}%)" if eoa_pct is not None else ""
        lines.append(f"• Excesso sobre o limite anômalo: +{_fmt(eoa)} {unit}{pct_str}")
    if duration_minutes is not None:
        if duration_minutes >= 60:
            dur = f"{duration_minutes / 60:.0f}h".replace(".", ",")
        else:
            dur = f"{duration_minutes:.0f} min"
        lines.append(f"• Janela analisada: {dur}")
    if composite_factors:
        lines.append(f"• Evidência composta: {', '.join(composite_factors)}")
    else:
        lines.append("• Sem evidência composta (queda isolada)")
    lines.append(f"• Confiança da baseline: {baseline_confidence}")
    motivo = _SEVERITY_REASON_LABELS.get(severity_reason.split("|")[0], severity_reason)
    lines.append(f"• Classificação: {severity} — {motivo}")
    return "\n".join(lines)


def _queda_nivel_recommendation(severity: str, level_pct: Optional[float]) -> str:
    """Recomendação proporcional para queda_nivel, considerando o nível atual."""
    safe = level_pct is None or level_pct >= _LEVEL_PCT_SAFE_FLOOR
    if severity == "atencao":
        return (
            "Acompanhar próximas leituras. Se a queda persistir ou o nível "
            "cair, investigar consumo anormal."
        )
    if severity == "moderado":
        return (
            "Verificar se houve consumo esperado no período. Se a queda "
            "continuar nas próximas leituras ou o nível se aproximar de "
            "faixa baixa, investigar possível consumo anormal ou vazamento."
        )
    # severity == "alto"
    if safe:
        return (
            "Investigar consumo anormal ou possível vazamento. "
            "Acompanhar até o nível estabilizar."
        )
    return (
        "Inspecionar pontos de saída e possível rompimento de tubulação. "
        "Nível já em faixa baixa."
    )


def _compute_drop_pph_now(
    series: list[SeriesPoint], now: datetime
) -> Optional[float]:
    """
    Queda de level_pct em p.p./h via regressão SUAVIZADA 1.5h.
    Usa smoothed_slope de signals.py para evitar falsos positivos por spikes
    de sensor nas pontas da janela.
    """
    return _drop_per_hour_smoothed(series, lookback_hours=1.5, now=now)


def _compute_drop_abs_2h_now(
    series: list[SeriesPoint], now: datetime
) -> Optional[float]:
    """
    Queda equivalente de level_pct em 2h estimada via regressão SUAVIZADA.
    Substitui a diferença de pontas (window[0] - window[-1]) que era frágil a
    spikes isolados no início ou no fim da janela — o FP clássico de
    'queda-enquanto-sobe'.

    Retorna: queda absoluta estimada = taxa_pph × 2.0 (p.p. em 2h).
    None se não há queda ou pontos insuficientes.
    """
    pph = _drop_per_hour_smoothed(series, lookback_hours=2.0, now=now)
    if pph is None or pph <= 0:
        return None
    # Converte taxa por hora em queda absoluta em 2h para comparar com a baseline
    # de `level_drop_abs_2h` (que mede p.p. acumulados em 2h).
    return pph * 2.0


def _severity_rank(severity: Optional[str]) -> int:
    return _SEV_ORDER.get(severity or "", 0)


def _safety_fallback_queda_nivel(
    series: list[SeriesPoint], now: datetime
) -> DetectorResult:
    """
    Fallback de segurança sem baseline tank_level: só dispara em queda extrema
    (≥30 p.p./h) com nível já baixo (≤50%). Severity sempre 'alto'.
    """
    result = DetectorResult(rule_key="queda_nivel", alert_type="nivel", is_active=False)
    nivel_atual = _last(series) or 0.0
    result.current_value = nivel_atual

    drop_pph = _compute_drop_pph_now(series, now)
    if drop_pph is None or drop_pph < _SAFETY_DROP_PPH_MIN or nivel_atual > _SAFETY_LEVEL_MAX:
        result.reason = "no_tank_level_behavior_baseline"
        return result

    result.is_active = True
    result.severity = "alto"
    result.titulo = "Nível caindo rapidamente — possível grande vazamento"
    result.mensagem_usuario = (
        f"• Queda de {_fmt(drop_pph)} p.p./hora (nível atual: {_fmt(nivel_atual)}%).\n"
        "• Baseline comportamental indisponível — critério de segurança ativado."
    )
    result.recomendacao = "Verificar pontos de saída e possível rompimento de tubulação."
    result.dados_relevantes = {
        "reason":            "safety_fallback_no_tank_level_baseline",
        "observed_value":    round(drop_pph, 1),
        "observed_unit":     "p.p./h",
        "level_pct_atual":   round(nivel_atual, 1),
        "channel_role":      "tank_level",
    }
    return result


# ── 9. queda_nivel ────────────────────────────────────────────────────────────

def detect_queda_nivel(ctx: InstallationContext, now: datetime) -> DetectorResult:
    cap = ctx.capabilities
    if cap is None or not cap.can_alert_level:
        return _inactive("queda_nivel", "nivel",
                         "not_applicable_without_tank_pressure")
    if _tank_sensor_failed(ctx):
        return _inactive("queda_nivel", "nivel", "tank_sensor_fault")

    series = ctx.series.get("level_pct", [])
    if len(series) < 4:
        result = DetectorResult(rule_key="queda_nivel", alert_type="nivel", is_active=False)
        result.reason = "insufficient_level_points"
        return result

    period      = _current_period_type(now)
    nivel_atual = _last(series) or 0.0  # necessário antes do loop para _severity_queda_nivel

    # Avalia as duas métricas comportamentais; escolhe a de maior severidade.
    candidates: list[tuple[str, str, str, float, dict, float]] = []
    for metric_key, compute_fn, duration_min in [
        ("level_drop_pph",    _compute_drop_pph_now,    90.0),
        ("level_drop_abs_2h", _compute_drop_abs_2h_now, 120.0),
    ]:
        observed = compute_fn(series, now)
        if observed is None or observed <= 0:
            continue
        ref = (
            behavior_ref(ctx, "tank_level", metric_key, period)
            or behavior_ref(ctx, "tank_level", metric_key, "overall")
        )
        if ref is None:
            continue
        normal_high  = ref.get("normal_high")
        anomaly_high = ref.get("anomaly_high")
        if normal_high is None or anomaly_high is None:
            continue
        sev, sev_reason = _severity_queda_nivel(
            observed=observed,
            normal_high=normal_high,
            anomaly_high=anomaly_high,
            baseline_confidence=ref.get("confidence", "low"),
            level_pct_atual=nivel_atual,
            has_composite_evidence=False,
            has_strong_composite_evidence=False,
        )
        if sev is not None:
            candidates.append((sev, sev_reason, metric_key, observed, ref, duration_min))

    if not candidates:
        return _safety_fallback_queda_nivel(series, now)

    # Maior severidade vence; desempate por maior excess_over_anomaly_pct.
    def _sort_key(c: tuple) -> tuple:
        sev, _, _, obs, ref, _ = c
        a_high = ref.get("anomaly_high") or 1.0
        excess_pct = (obs - a_high) / a_high * 100 if a_high > 0 else 0.0
        return (_severity_rank(sev), excess_pct)

    candidates.sort(key=_sort_key, reverse=True)
    sev, sev_reason, metric_key, observed, ref, duration_min = candidates[0]

    unit   = "p.p./h" if metric_key == "level_drop_pph" else "p.p. em 2h"
    excess = _excess_fields(observed, ref.get("normal_high"), ref.get("anomaly_high"))
    conf   = ref.get("confidence", "low")

    result = DetectorResult(rule_key="queda_nivel", alert_type="nivel", is_active=True)
    result.severity      = sev
    result.current_value = nivel_atual
    result.titulo        = "Queda acelerada de nível — investigar causa"
    result.mensagem_usuario = _queda_nivel_message(
        nivel_atual=nivel_atual,
        observed=observed,
        unit=unit,
        normal_high=ref.get("normal_high"),
        anomaly_high=ref.get("anomaly_high"),
        excess=excess,
        period_type=period,
        baseline_confidence=conf,
        severity=sev,
        severity_reason=sev_reason,
        composite_factors=[],
        duration_minutes=duration_min,
    )
    result.recomendacao = _queda_nivel_recommendation(sev, nivel_atual)
    result.dados_relevantes = _behavior_dados(
        ref, metric_key, period, observed,
        _window_points(series, int(duration_min), now),
        reason="level_drop_above_installation_reference",
        severity_reason=sev_reason,
        excess=excess,
        composite_evidence=False,
        strong_composite_evidence=False,
        composite_evidence_factors=[],
        duration_minutes=duration_min,
    )
    # _behavior_dados assume flow — corrige campos específicos de nível.
    result.dados_relevantes["channel_role"]    = "tank_level"
    result.dados_relevantes["observed_unit"]   = unit
    result.dados_relevantes["metric_used"]     = metric_key
    result.dados_relevantes["level_pct_atual"] = round(nivel_atual, 1)
    return result


# ── 10. behavior_baseline_stale (infra — baseline comportamental desatualizado) ──

def detect_behavior_baseline_stale(
    ctx: InstallationContext,
    now: datetime,
) -> DetectorResult:
    """
    Fase 11 — Detecta que o behavior_baseline_worker não recalculou a baseline
    desta instalação há mais de _BEHAVIOR_STALE_HOURS horas.

    Só dispara se a baseline JÁ FOI calculada antes (last_computed não é None):
    - None → worker nunca rodou ou instalação muito nova → inativo, sem alarme.
    - > 26h → timer diário pode estar quebrado → moderado.

    Independente de baseline comportamental (não usa behavior_ref).
    """
    cap = ctx.capabilities
    # Só relevante para instalações com canais de vazão monitorados.
    if cap is None or not (cap.has_street_inlet_counter or cap.has_tank_outlet_counter):
        return _inactive("behavior_baseline_stale", "infraestrutura",
                         "not_applicable_no_flow_channel")

    last_computed = ctx.behavior_last_computed
    if last_computed is None:
        # Baseline nunca calculado — normal para instalações novas ou
        # antes do primeiro deploy do worker.
        return _inactive("behavior_baseline_stale", "infraestrutura",
                         "baseline_never_computed")

    age_hours = (now - last_computed).total_seconds() / 3600
    result = DetectorResult(rule_key="behavior_baseline_stale",
                            alert_type="infraestrutura", is_active=False)
    result.current_value = round(age_hours, 1)
    result.dados_relevantes = {
        "last_computed_at": last_computed.isoformat(),
        "age_hours":        round(age_hours, 1),
        "threshold_hours":  _BEHAVIOR_STALE_HOURS,
    }

    if age_hours >= _BEHAVIOR_STALE_HOURS:
        result.is_active = True
        result.severity  = "moderado"
        result.titulo    = "Baseline comportamental desatualizado"
        result.mensagem_usuario = (
            f"O baseline de 30 dias desta instalação não foi recalculado há "
            f"{age_hours:.0f}h (limite: {_BEHAVIOR_STALE_HOURS:.0f}h). "
            "O timer diário do behavior_baseline_worker pode estar com problema."
        )
        result.recomendacao = (
            "Verificar: systemctl status telemetry-worker-behavior-baseline.timer"
        )

    return result


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def _run_pipeline(ctx: InstallationContext, now: datetime,
                  baseline_ready: bool, is_stale: bool,
                  in_learning: bool) -> list[DetectorResult]:
    """
    Executa os detectores e retorna lista de resultados.

    Categorias:
      A) Sempre: sem_comunicacao.
      B) Não stale: detectores hidráulicos. Cada um faz GATE de capacidade
         internamente — se a instalação não tem o canal/capacidade, retorna
         inativo explícito (resolve alertas presos). Não há early-return por
         capacidade; só `is_stale` preserva o estado hidráulico (não reavalia
         para não resolver um problema real apenas por falta de dado novo).

    Detectores estatísticos recebem `baseline_ok`: se False (baseline não pronto
    ou em aprendizado) retornam inativo — continuam na lista, resolvendo estados
    antigos, sem calcular estatística.
    """
    results: list[DetectorResult] = []

    # Categoria A — sempre
    results.append(detect_sem_comunicacao(ctx, now))

    # Stale: não reavalia hidráulicos (preserva estado). sem_comunicacao cobre.
    if is_stale:
        return results

    baseline_ok = baseline_ready and not in_learning

    # Categoria B — failsafes + técnicos de rua/caixa + pressão + infra
    results.append(detect_sensor_invalido(ctx))
    results.append(detect_sensor_pressao_rua_falha(ctx, now))
    results.append(detect_remota_sem_leitura(ctx, now))
    results.append(detect_caixa_sem_pressao(ctx, now))
    results.append(detect_nivel_baixo(ctx))
    results.append(detect_autonomia_insuficiente(ctx))
    results.append(detect_queda_nivel(ctx, now))
    results.append(detect_pressao_rua_baixa(ctx, now))
    results.append(detect_behavior_baseline_stale(ctx, now))  # Fase 11

    # Categoria C — estatísticos (gate de capacidade + baseline_ok internos)
    results.append(detect_consumo_acima_media(ctx, now, baseline_ok))
    results.append(detect_consumo_baixo(ctx, now, baseline_ok))
    results.append(detect_consumo_sem_repouso(ctx, now, baseline_ok))
    results.append(detect_vazamento_noturno(ctx, now, baseline_ok))
    results.append(detect_vazamento_composto(ctx, now, baseline_ok))
    results.append(detect_consumo_ininterrupto(ctx, now, baseline_ok))
    results.append(detect_vazao_noturna(ctx, now, baseline_ok))
    results.append(detect_pico_consumo(ctx, now, baseline_ok))
    results.append(detect_variacao_rapida(ctx, now, baseline_ok))
    results.append(detect_vazamento_pos_caixa(ctx, now, baseline_ok))

    _suppress_duplicate_velocity(results, ctx)

    return results


def _suppress_duplicate_velocity(
    results: list[DetectorResult],
    ctx: InstallationContext,
) -> None:
    """
    Anti-duplicação: quando `pico_consumo` já disparou para o canal de consumo
    com severidade ≥ à de `variacao_rapida` no MESMO canal, suprime
    `variacao_rapida` (o pico já comunica o evento). Mutação in-place.
    """
    pico = next((r for r in results if r.rule_key == "pico_consumo"), None)
    if pico is None or not pico.is_active or pico.severity is None:
        return
    pico_metric = consumption_metric(ctx.capabilities) if ctx.capabilities else None
    for i, r in enumerate(results):
        if r.rule_key != "variacao_rapida" or not r.is_active or r.severity is None:
            continue
        var_metric = (r.dados_relevantes or {}).get("metric_used")
        if var_metric == pico_metric and _SEV_ORDER[pico.severity] >= _SEV_ORDER[r.severity]:
            results[i] = _inactive("variacao_rapida", r.alert_type,
                                   "deferred_to_pico_consumo")


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class AlertWorker:
    """Avalia detectores de alerta periodicamente para cada instalação ativa."""

    worker_name = "alert_worker"

    def __init__(self) -> None:
        self._settings = get_settings()
        self._running  = True
        self._log      = logger.bind(worker=self.worker_name)
        # Cache: installation_id → última marca de INGESTÃO vista (MAX created_at).
        # Usar ingestão (não derived_at_utc) garante reavaliação de histórico
        # atrasado em burst do Dragino — leituras de timestamp passado.
        self._last_ingest_seen: dict[int, datetime] = {}
        # IDs de alert_events CRÍTICOS recém-criados, aguardando enfileiramento
        # de notificação Telegram. Drenado após o commit do alerta.
        self._pending_telegram_events: list[int] = []

    async def run(self) -> None:
        s = self._settings
        self._log.info(f"{self.worker_name}.starting",
                       interval=s.worker_alert_interval_seconds)

        while self._running:
            try:
                # ── Disparo encadeado: avalia instalações sinalizadas pelo derive_worker.
                # Prioridade sobre o ciclo completo; o ciclo completo é rede de segurança.
                dirty_ids = await _drain_dirty()
                if dirty_ids:
                    async with get_session() as session:
                        await self._evaluate_by_ids(session, dirty_ids)

                async with get_session() as session:
                    await self._evaluate_all(session)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._log.error(f"{self.worker_name}.loop_error",
                                error=str(exc), exc_info=True)

            await asyncio.sleep(s.worker_alert_interval_seconds)

        self._log.info(f"{self.worker_name}.stopped")

    def stop(self) -> None:
        self._running = False

    # ── Ciclo principal ───────────────────────────────────────────────────────

    async def _evaluate_by_ids(
        self, session: AsyncSession, ids: frozenset[int]
    ) -> None:
        """Avalia somente as instalações cujos IDs estão em `ids`.

        Chamado pelo disparo encadeado (drain_dirty) para priorizar instalações
        com dados novos antes do ciclo completo de rede de segurança.
        """
        if not ids:
            return
        result = await session.execute(
            _SQL_INSTALLATIONS_BY_IDS, {"ids": list(ids)}
        )
        installations = result.fetchall()
        if not installations:
            return

        now = datetime.now(timezone.utc)
        for inst_id, slug, learning_mode_until, baseline_ready_at in installations:
            try:
                await self._evaluate_installation(
                    session, inst_id, slug,
                    learning_mode_until, baseline_ready_at, now
                )
                await session.commit()
                pending_tg = self._pending_telegram_events[:]
                self._pending_telegram_events = []
                if pending_tg:
                    try:
                        async with get_session() as notif_session:
                            for event_id in pending_tg:
                                await enqueue_critical_alert_user_notifications(
                                    notif_session, event_id
                                )
                    except Exception as exc_tg:
                        self._log.error(
                            f"{self.worker_name}.telegram_enqueue_error",
                            error=str(exc_tg), exc_info=True,
                        )
            except Exception as exc:
                self._pending_telegram_events = []
                await session.rollback()
                self._log.error(f"{self.worker_name}.dirty_inst_error",
                                installation=slug, error=str(exc), exc_info=True)

        self._log.debug(f"{self.worker_name}.dirty_cycle_done",
                        evaluated=len(installations), dirty_ids=len(ids))

    async def _evaluate_all(self, session: AsyncSession) -> None:
        result = await session.execute(_SQL_INSTALLATIONS)
        installations = result.fetchall()
        if not installations:
            return

        now = datetime.now(timezone.utc)
        total_active = 0

        for inst_id, slug, learning_mode_until, baseline_ready_at in installations:
            try:
                count = await self._evaluate_installation(
                    session, inst_id, slug,
                    learning_mode_until, baseline_ready_at, now
                )
                total_active += count
                await session.commit()
                pending_tg = self._pending_telegram_events[:]
                self._pending_telegram_events = []
                if pending_tg:
                    try:
                        async with get_session() as notif_session:
                            for event_id in pending_tg:
                                await enqueue_critical_alert_user_notifications(
                                    notif_session, event_id
                                )
                    except Exception as exc_tg:
                        self._log.error(
                            f"{self.worker_name}.telegram_enqueue_error",
                            error=str(exc_tg), exc_info=True,
                        )
            except Exception as exc:
                self._pending_telegram_events = []
                await session.rollback()
                self._log.error(f"{self.worker_name}.inst_error",
                                installation=slug, error=str(exc), exc_info=True)

        self._log.info(f"{self.worker_name}.cycle_done",
                       installations=len(installations),
                       active_alerts=total_active)

    async def _evaluate_installation(
        self,
        session: AsyncSession,
        inst_id: int,
        slug: str,
        learning_mode_until: Optional[datetime],
        baseline_ready_at: Optional[datetime],
        now: datetime,
    ) -> int:
        # ── 1. Latest timestamp (horário da leitura) — para staleness ─────────
        ts_result = await session.execute(
            _SQL_LATEST_TS, {"installation_id": inst_id}
        )
        latest_ts: Optional[datetime] = ts_result.scalar()

        # ── 1b. Marca de ingestão (MAX created_at) — detecta histórico atrasado ─
        ingest_result = await session.execute(
            _SQL_LATEST_INGEST, {"installation_id": inst_id}
        )
        latest_ingest: Optional[datetime] = ingest_result.scalar()

        is_stale   = (
            latest_ts is not None
            and (now - latest_ts).total_seconds() > _STALE_HOURS * 3600
        )
        in_learning = (
            learning_mode_until is not None
            and learning_mode_until > now
        )
        # ── 2. Reactive check (sem INGESTÃO nova desde o último ciclo) ────────
        # Gatilho por ingestão: um burst com leituras de timestamp passado
        # avança created_at mesmo sem novo derived_at_utc → reavalia o evento.
        last_seen = self._last_ingest_seen.get(inst_id)
        new_data  = latest_ingest is not None and (
            last_seen is None or latest_ingest > last_seen
        )

        if not new_data and latest_ts is not None:
            # Só sem_comunicacao precisa de re-avaliação sem dados novos
            ctx = InstallationContext(
                inst_id=inst_id, slug=slug,
                learning_mode_until=learning_mode_until,
                baseline_ready_at=baseline_ready_at,
                latest_ts=latest_ts,
                settings=get_settings(),
            )
            det = detect_sem_comunicacao(ctx, now)
            states_result = await session.execute(
                _SQL_STATES, {"installation_id": inst_id}
            )
            states = {row[0]: row for row in states_result.fetchall()}
            await self._apply_result(session, inst_id, slug, det, states, now)
            return 1 if det.is_active else 0

        if latest_ingest is not None:
            self._last_ingest_seen[inst_id] = latest_ingest

        # ── 3. Carrega séries ─────────────────────────────────────────────────
        # 3a. Métricas não-flow (level, pressão, temp, autonomia) de derived_metrics
        series_result = await session.execute(
            _SQL_SERIES, {"installation_id": inst_id}
        )
        ctx = InstallationContext(
            inst_id=inst_id, slug=slug,
            learning_mode_until=learning_mode_until,
            baseline_ready_at=baseline_ready_at,
            latest_ts=latest_ts,
        )

        for metric_name, value, derived_at in series_result.fetchall():
            if value is None:
                continue
            ctx.series.setdefault(metric_name, []).append(
                SeriesPoint(ts=derived_at, value=float(value))
            )

        # 3b. Vazão via janela deslizante de 1h sobre contadores acumulados.
        # Elimina spikes causados por históricos do Dragino com Δt pequeno.
        # O mesmo algoritmo usado pelo gráfico (dashboardMetrics.ts:computeFlowSeries).
        counts_result = await session.execute(
            _SQL_COUNTS, {"installation_id": inst_id}
        )
        count_rows = counts_result.fetchall()  # (collected_at_utc, count_pulses, count2_pulses)
        if count_rows:
            lpp = float(get_settings().flow_liter_per_pulse)
            pts1 = [(ts, c1) for ts, c1, _c2 in count_rows]
            pts2 = [(ts, c2) for ts, _c1, c2 in count_rows]
            flow1 = windowed_flow_series(pts1, liter_per_pulse=lpp)
            flow2 = windowed_flow_series(pts2, liter_per_pulse=lpp)
            for ts, v in flow1:
                ctx.series.setdefault("flow1_lph", []).append(SeriesPoint(ts=ts, value=v))
            for ts, v in flow2:
                ctx.series.setdefault("flow2_lph", []).append(SeriesPoint(ts=ts, value=v))
            # Total: soma alinhada por índice (mesma lógica do frontend)
            for (ts, v1), (_, v2) in zip(flow1, flow2):
                ctx.series.setdefault("flow_total_lph", []).append(
                    SeriesPoint(ts=ts, value=v1 + v2)
                )

        # 3c. Série longa (30 dias) para o detector de vazamento noturno.
        # Query separada para não alterar custo/semântica dos outros detectores.
        leak_result = await session.execute(
            _SQL_COUNTS_LEAK, {"installation_id": inst_id}
        )
        leak_rows = leak_result.fetchall()
        if leak_rows:
            lpp_leak = float(get_settings().flow_liter_per_pulse)
            lpts1 = [(ts, c1) for ts, c1, _c2 in leak_rows]
            lpts2 = [(ts, c2) for ts, _c1, c2 in leak_rows]
            lflow1 = windowed_flow_series(lpts1, liter_per_pulse=lpp_leak)
            lflow2 = windowed_flow_series(lpts2, liter_per_pulse=lpp_leak)
            for ts, v in lflow1:
                ctx.long_series.setdefault("flow1_lph", []).append(SeriesPoint(ts=ts, value=v))
            for ts, v in lflow2:
                ctx.long_series.setdefault("flow2_lph", []).append(SeriesPoint(ts=ts, value=v))

        if not ctx.series and not is_stale:
            return 0

        # ── 4. Baselines globais ──────────────────────────────────────────────
        bl_result = await session.execute(
            _SQL_BASELINES, {"installation_id": inst_id}
        )
        for (
            mn,
            mean,
            std,
            p10,
            p90,
            sample_count,
            window_days,
            _computed_at,
        ) in bl_result.fetchall():
            ctx.baselines[mn] = {
                "mean": float(mean or 0),
                "std":  float(std  or 0),
                "p10":  float(p10  or 0) if p10  is not None else 0.0,
                "p90":  float(p90  or 0) if p90  is not None else 0.0,
                "sample_count": float(sample_count or 0),
                "window_days":  float(window_days or 0),
            }
        baseline_ready = bool(ctx.baselines)

        # Overrides e snoozes desabilitados: tabelas não existem no schema 0008.
        # ctx.overrides = {} (default) → _get_param usa defaults.
        # ctx.active_snoozes = set() (default) → sem supressão.

        # ── 6. Estados anteriores ─────────────────────────────────────────────
        states_result = await session.execute(
            _SQL_STATES, {"installation_id": inst_id}
        )
        states = {row[0]: row for row in states_result.fetchall()}

        # Popula prior_alert_states para que detectores acessem dados_relevantes anteriores.
        for rule_key, row in states.items():
            raw_dr = row[7]  # dados_relevantes — nova coluna no fim do SELECT
            if isinstance(raw_dr, str):
                try:
                    raw_dr = json.loads(raw_dr)
                except Exception:
                    raw_dr = {}
            ctx.prior_alert_states[rule_key] = {
                "is_active":          bool(row[1]),
                "first_triggered_at": row[2],
                "dados_relevantes":   raw_dr if isinstance(raw_dr, dict) else {},
            }

        # ── 6b. Capacidades hidráulicas inferidas dos dados (cache + TTL) ──────
        ctx.capabilities = await get_installation_capabilities(
            inst_id, session, slug=slug
        )

        # ── 6c. Baseline comportamental (Fase 5 — read-only, sem alterar alertas) ──
        beh_result = await session.execute(
            _SQL_BEHAVIOR, {"installation_id": inst_id}
        )
        beh_rows = beh_result.fetchall()
        for row in beh_rows:
            key = (row.channel_role, row.metric_name, row.period_type)
            ctx.behavior[key] = {
                "normal_low":         row.normal_low,
                "normal_high":        row.normal_high,
                "anomaly_low":        row.anomaly_low,
                "anomaly_high":       row.anomaly_high,
                "minimum_night_flow": row.minimum_night_flow,
                "profile_type":       row.profile_type,
                "confidence":         row.confidence,
                "zero_ratio":         row.zero_ratio,
                "near_zero_ratio":    row.near_zero_ratio,
                "p50":                row.p50,
                "p90":                row.p90,
                "sample_count":       row.sample_count,
                "typical_variation_per_hour": row.typical_variation_per_hour,
            }

        # MAX(computed_at) das linhas carregadas → usado por detect_behavior_baseline_stale.
        if beh_rows:
            computed_times = [r.computed_at for r in beh_rows if r.computed_at is not None]
            if computed_times:
                ctx.behavior_last_computed = max(computed_times)

        if beh_rows:
            channels_loaded = sorted({
                (r.channel_role, r.metric_name) for r in beh_rows
            })
            self._log.info(
                f"{self.worker_name}.behavior_baseline_loaded",
                installation=slug,
                rows=len(beh_rows),
                channels=channels_loaded,
            )
            low_conf = [
                f"{r.channel_role}/{r.metric_name}/{r.period_type}"
                for r in beh_rows if r.confidence == "low"
            ]
            if low_conf:
                self._log.info(
                    f"{self.worker_name}.behavior_baseline_confidence_low",
                    installation=slug,
                    low_confidence_slots=low_conf[:10],  # trunca para não inchar log
                )
        else:
            cap = ctx.capabilities
            if cap is not None:
                missing: list[tuple[str, str]] = []
                if cap.has_street_inlet_counter:
                    missing.append(("street_inlet", "flow1_lph"))
                if cap.has_tank_outlet_counter:
                    missing.append(("tank_outlet", "flow2_lph"))
                if missing:
                    self._log.info(
                        f"{self.worker_name}.behavior_baseline_missing",
                        installation=slug,
                        expected_channels=missing,
                    )

        # ── 7. Executa pipeline ───────────────────────────────────────────────
        detector_results = _run_pipeline(
            ctx, now,
            baseline_ready=baseline_ready,
            is_stale=is_stale,
            in_learning=in_learning,
        )

        # ── 7b. Shadow mode (Fase 6) — comparação comportamental ─────────────
        # Loga legacy vs comportamental para os 5 detectores de consumo/vazão.
        # Não altera alert_state, alert_events nem nenhuma decisão real.
        if ctx.behavior and not is_stale:
            _shadow_log_compare(
                self._log, self.worker_name, ctx, now, detector_results
            )

        # ── 8. Injeta event_time e aplica snoozes ─────────────────────────────
        event_time = latest_ts.isoformat() if latest_ts else now.isoformat()
        all_snoozed = None in ctx.active_snoozes  # snooze de instalação inteira

        active_count = 0
        for det in detector_results:
            if det.is_active:
                # Injeta event_time
                if det.dados_relevantes is None:
                    det.dados_relevantes = {}
                det.dados_relevantes.setdefault("event_time", event_time)

                # Aplica snooze
                if all_snoozed or det.rule_key in ctx.active_snoozes:
                    det.is_active = False
                    det.dados_relevantes["snoozed"] = True

            # Shadow-only: log estruturado sem tocar em alert_state/alert_events.
            # Permite observar 24-48h antes de ativar como alerta real.
            if det.rule_key in _SHADOW_ONLY_RULES:
                if det.is_active:
                    self._log.info(
                        f"{self.worker_name}.shadow_fire",
                        installation=slug,
                        rule_key=det.rule_key,
                        severity=det.severity,
                        titulo=det.titulo,
                        current_value=det.current_value,
                        dados_relevantes=det.dados_relevantes,
                    )
                continue  # não grava no banco

            await self._apply_result(session, inst_id, slug, det, states, now)
            if det.is_active:
                active_count += 1

        return active_count

    async def _apply_result(
        self,
        session: AsyncSession,
        inst_id: int,
        slug: str,
        det: DetectorResult,
        states: dict,
        now: datetime,
    ) -> None:
        prev = states.get(det.rule_key)
        was_active = bool(prev[1]) if prev else False

        fired     = det.is_active and not was_active
        resolved  = not det.is_active and was_active
        sustained = det.is_active and was_active

        dados_json = json.dumps(det.dados_relevantes) if det.dados_relevantes else None

        await session.execute(
            _SQL_UPSERT_STATE,
            {
                "installation_id":   inst_id,
                "rule_key":          det.rule_key,
                "is_active":         det.is_active,
                "alert_type":        det.alert_type,
                "severity":          det.severity if det.is_active else None,
                "titulo":            det.titulo if det.is_active else None,
                "mensagem_usuario":  det.mensagem_usuario if det.is_active else None,
                "recomendacao":      det.recomendacao if det.is_active else None,
                "dados_relevantes":  dados_json if det.is_active else None,
                "current_value":     det.current_value,
                "first_triggered_at": now if fired else None,
                "last_triggered_at":  now if det.is_active else None,
                "last_resolved_at":   now if resolved else None,
            },
        )

        if fired:
            _event_row = (await session.execute(
                _SQL_INSERT_EVENT,
                {
                    "installation_id": inst_id,
                    "rule_key":        det.rule_key,
                    "alert_type":      det.alert_type,
                    "severity":        det.severity or "atencao",
                    "message":         det.mensagem_usuario or det.titulo or det.rule_key,
                    "titulo":          det.titulo,
                    "mensagem_usuario": det.mensagem_usuario,
                    "recomendacao":    det.recomendacao,
                    "dados_relevantes": dados_json,
                    "status":          "ativo",
                    "current_value":   det.current_value,
                },
            )).first()
            if _event_row and is_critical_severity(det.severity):
                self._pending_telegram_events.append(_event_row[0])
            self._log.warning(
                f"{self.worker_name}.alert_fired",
                installation=slug, rule=det.rule_key,
                severity=det.severity, titulo=det.titulo,
            )

        elif resolved:
            prev_severity = prev[6] if prev else "atencao"
            await session.execute(
                _SQL_INSERT_EVENT,
                {
                    "installation_id": inst_id,
                    "rule_key":        det.rule_key,
                    "alert_type":      det.alert_type,
                    "severity":        prev_severity or "atencao",
                    "message":         f"Resolvido: {det.rule_key}",
                    "titulo":          None,
                    "mensagem_usuario": None,
                    "recomendacao":    None,
                    "dados_relevantes": None,
                    "status":          "resolvido",
                    "current_value":   det.current_value,
                },
            )
            self._log.info(
                f"{self.worker_name}.alert_resolved",
                installation=slug, rule=det.rule_key,
            )

        elif sustained:
            metric_used = (
                det.dados_relevantes.get("metric_used")
                if det.dados_relevantes
                else None
            )
            await session.execute(
                _SQL_UPDATE_ACTIVE_EVENT,
                {
                    "installation_id": inst_id,
                    "rule_key":        det.rule_key,
                    "severity":        det.severity or "atencao",
                    "titulo":          det.titulo,
                    "mensagem_usuario": det.mensagem_usuario,
                    "recomendacao":    det.recomendacao,
                    "message":         det.mensagem_usuario or det.titulo or det.rule_key,
                    "dados_relevantes": dados_json,
                    "current_value":   det.current_value,
                    "metric_used":     metric_used,
                },
            )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def _main() -> None:
    from app.config import get_settings
    from app.logging import configure_logging

    s = get_settings()
    configure_logging(log_level=s.log_level, log_format=s.log_format)
    await AlertWorker().run()


if __name__ == "__main__":
    asyncio.run(_main())
