"""
app/alerts/behavior.py — Cálculo puro do baseline comportamental por instalação.

Fornece funções stateless para transformar uma série (timestamp, value) no
conjunto de campos da tabela installation_behavior_baselines. Não acessa banco,
não é async, não importa app.db.

Uso esperado pelo behavior_baseline_worker (Fase 3):
    from app.alerts.behavior import compute_baseline_row, period_types_for, to_brt

Filosofia de limites: normal_high e anomaly_high derivam dos PERCENTIS da
própria instalação — jamais de valores absolutos de L/h. O único valor absoluto
permitido é NEAR_ZERO_FLOW_LPH, critério TÉCNICO de repouso documentado abaixo.

Debug / sanidade rápida:
    python3 -c "from datetime import datetime, timezone; \
import app.alerts.behavior as b; ts=datetime(2026,6,2,4,0,tzinfo=timezone.utc); \
print(b.period_types_for(b.to_brt(ts)))"
"""
from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Constantes centralizadas
# ---------------------------------------------------------------------------

# Offset fixo BRT (UTC-3). O Brasil não adota mais horário de verão desde 2019;
# todo o código existente usa -3 fixo (alert_worker.py:374, menu.py:50).
BRT_OFFSET_HOURS: int = -3

# Critério TÉCNICO de repouso — NÃO é regra de consumo/anomalia.
# Um ponto é "em repouso" quando vazão <= este valor. Usado APENAS para:
#   - zero_ratio / near_zero_ratio
#   - identificação de runs de repouso e fluxo contínuo
# Em L/h. Conservador (1 L/h) para não mascarar repouso real.
NEAR_ZERO_FLOW_LPH: float = 1.0

# Tolerância de "zero exato" com ruído de sensor.
ZERO_EPS: float = 1e-6

# Fronteiras de período em hora BRT (inteiros, início inclusivo, fim exclusivo).
NIGHT_START_HOUR: int = 0    # night  = [00:00, 06:00) BRT
NIGHT_END_HOUR: int = 6
DAY_START_HOUR: int = 6      # day    = [06:00, 24:00) BRT
BUSINESS_START_HOUR: int = 7  # seg–sex [07:00, 18:00) BRT
BUSINESS_END_HOUR: int = 18

# Multiplicador de Tukey (IQR) para limites de anomalia.
# 1.5 é o padrão (boxplot), mantém conservadorismo — prefere falso negativo
# a falso positivo.
ANOMALY_IQR_K: float = 1.5

# Bandas de confiança por dias efetivos cobertos (relatório seção 10.6).
CONF_MEDIUM_DAYS: int = 8
CONF_HIGH_DAYS: int = 15
CONF_CONSOLIDATED_DAYS: int = 30

# Piso mínimo de amostras para sair de "low" (proteção para janelas curtas com
# poucos pontos mas alta cobertura aparente, ex.: 7 dias × 1 ponto/dia).
MIN_SAMPLES_FOR_CONFIDENCE: int = 50

# Limiares de FORMATO para profile_type. Baseados em proporções, nunca em
# magnitudes absolutas — respeita a regra "sem thresholds universais".
PROFILE_INACTIVE_ZERO_RATIO: float = 0.95     # canal praticamente não flui
PROFILE_CONTINUOUS_REST_RATIO: float = 0.05   # quase não descansa → contínuo
PROFILE_INTERMITTENT_REST_RATIO: float = 0.60  # descansa a maior parte do tempo


# ---------------------------------------------------------------------------
# 1. Tempo / período
# ---------------------------------------------------------------------------

def to_brt(ts: datetime) -> datetime:
    """
    Converte um datetime UTC para BRT (UTC-3, offset fixo).

    Converte a data completa (não só a hora) para que weekday() e
    hour fiquem corretos quando o offset cruza a meia-noite.

    Args:
        ts: datetime com tzinfo UTC ou aware qualquer.

    Returns:
        datetime em UTC-3 (tzinfo=timezone(timedelta(hours=-3))).
    """
    brt_tz = timezone(timedelta(hours=BRT_OFFSET_HOURS))
    return ts.astimezone(brt_tz)


def period_types_for(ts_brt: datetime) -> tuple[str, ...]:
    """
    Retorna todos os períodos a que o instante (já em BRT) pertence.

    Um instante sempre cai em exatamente 3 períodos:
        overall + (night | day) + (business_hours | off_hours | weekend)

    Valores possíveis: overall, night, day, business_hours, off_hours, weekend.

    Args:
        ts_brt: datetime já convertido para BRT (via to_brt).

    Returns:
        Tupla imutável de 3 strings de período.
    """
    h = ts_brt.hour
    wd = ts_brt.weekday()  # 0=seg … 4=sex, 5=sáb, 6=dom

    # Período de hora do dia
    time_period = "night" if NIGHT_START_HOUR <= h < NIGHT_END_HOUR else "day"

    # Período de uso operacional
    is_weekend = wd >= 5  # sáb ou dom
    if is_weekend:
        usage_period = "weekend"
        # fim de semana também é off_hours — adicionamos os dois
        return ("overall", time_period, "weekend", "off_hours")

    # Dia útil
    if BUSINESS_START_HOUR <= h < BUSINESS_END_HOUR:
        usage_period = "business_hours"
    else:
        usage_period = "off_hours"

    return ("overall", time_period, usage_period)


# ---------------------------------------------------------------------------
# 2. Estatística descritiva
# ---------------------------------------------------------------------------

def percentile(values: list[float], p: float) -> float:
    """
    Percentil via interpolação linear. Algoritmo idêntico a
    baseline_worker._percentile para consistência com baselines existentes.

    Args:
        values: lista de floats (não precisa estar ordenada).
        p:      percentil em 0–100.

    Returns:
        Valor interpolado. Lista vazia → 0.0.
    """
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n == 1:
        return s[0]
    rank = p / 100.0 * (n - 1)
    lo = int(rank)
    hi = lo + 1
    frac = rank - lo
    if hi >= n:
        return s[-1]
    return s[lo] + frac * (s[hi] - s[lo])


def compute_statistics(values: list[float]) -> dict[str, Any]:
    """
    Calcula estatísticas descritivas completas.

    Args:
        values: lista de floats (valores da série no período).

    Returns:
        Dicionário com chaves:
            mean, std, min, max, p05, p10, p25, p50, p75, p90, p95.
        Lista vazia → mean=0.0, std=0.0, demais None.
    """
    if not values:
        return {
            "mean": 0.0, "std": 0.0,
            "min": None, "max": None,
            "p05": None, "p10": None, "p25": None, "p50": None,
            "p75": None, "p90": None, "p95": None,
        }

    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0

    return {
        "mean": mean,
        "std": std,
        "min": min(values),
        "max": max(values),
        "p05": percentile(values, 5),
        "p10": percentile(values, 10),
        "p25": percentile(values, 25),
        "p50": percentile(values, 50),
        "p75": percentile(values, 75),
        "p90": percentile(values, 90),
        "p95": percentile(values, 95),
    }


# ---------------------------------------------------------------------------
# 3. Repouso e fluxo contínuo
# ---------------------------------------------------------------------------

def zero_ratios(
    values: list[float],
    near_zero_threshold: float = NEAR_ZERO_FLOW_LPH,
) -> tuple[float, float]:
    """
    Calcula a fração de pontos "zerados" e "próximos de zero".

    Critério TÉCNICO de repouso — não é regra de anomalia.

    Args:
        values:              série de valores de vazão.
        near_zero_threshold: limiar de repouso em L/h (centralizado em
                             NEAR_ZERO_FLOW_LPH; passável para testes).

    Returns:
        (zero_ratio, near_zero_ratio):
            zero_ratio      = fração com |v| <= ZERO_EPS
            near_zero_ratio = fração com v <= near_zero_threshold
        Lista vazia → (0.0, 0.0).
    """
    if not values:
        return 0.0, 0.0
    n = len(values)
    zeros = sum(1 for v in values if abs(v) <= ZERO_EPS)
    near = sum(1 for v in values if v <= near_zero_threshold)
    return zeros / n, near / n


def _run_durations_minutes(
    values: list[float],
    timestamps: list[datetime],
    threshold: float,
    *,
    active: bool,
) -> list[float]:
    """
    Identifica runs maximais de pontos em estado "ativo" ou "em repouso"
    e retorna a duração de cada run em minutos.

    Args:
        values:     série de valores alinhada com timestamps.
        timestamps: datetimes correspondentes (podem ser UTC ou BRT;
                    usado só para calcular Δt).
        threshold:  limiar de repouso em L/h.
        active:     True  → runs com v > threshold (fluxo ativo).
                    False → runs com v <= threshold (repouso).

    Returns:
        Lista de durações (float, minutos). Run de 1 ponto → 0.0.
    """
    if not values or len(values) != len(timestamps):
        return []

    def _in_state(v: float) -> bool:
        return v > threshold if active else v <= threshold

    durations: list[float] = []
    run_start_idx: Optional[int] = None

    for i, v in enumerate(values):
        if _in_state(v):
            if run_start_idx is None:
                run_start_idx = i
        else:
            if run_start_idx is not None:
                dt = (
                    timestamps[i - 1] - timestamps[run_start_idx]
                ).total_seconds() / 60.0
                durations.append(max(0.0, dt))
                run_start_idx = None

    # Fecha run que termina no último ponto.
    if run_start_idx is not None:
        dt = (
            timestamps[-1] - timestamps[run_start_idx]
        ).total_seconds() / 60.0
        durations.append(max(0.0, dt))

    return durations


def rest_run_minutes(
    values: list[float],
    timestamps: list[datetime],
    threshold: float = NEAR_ZERO_FLOW_LPH,
) -> tuple[Optional[float], Optional[float]]:
    """
    Duração dos runs de REPOUSO (v <= threshold).

    Args:
        values:     série de vazão.
        timestamps: datetimes correspondentes.
        threshold:  limiar de repouso em L/h.

    Returns:
        (longest_zero_minutes, typical_zero_minutes)
        typical = mediana das durações.
        None em ambos se não houver nenhum run de repouso.
    """
    durations = _run_durations_minutes(values, timestamps, threshold, active=False)
    if not durations:
        return None, None
    return max(durations), statistics.median(durations)


def flow_run_minutes(
    values: list[float],
    timestamps: list[datetime],
    threshold: float = NEAR_ZERO_FLOW_LPH,
) -> tuple[Optional[float], Optional[float]]:
    """
    Duração dos runs de FLUXO CONTÍNUO (v > threshold).

    Args:
        values:     série de vazão.
        timestamps: datetimes correspondentes.
        threshold:  limiar de repouso em L/h.

    Returns:
        (longest_continuous_flow_minutes, typical_continuous_flow_minutes)
        typical = mediana das durações.
        None em ambos se não houver nenhum run ativo.
    """
    durations = _run_durations_minutes(values, timestamps, threshold, active=True)
    if not durations:
        return None, None
    return max(durations), statistics.median(durations)


def minimum_night_flow(values: list[float]) -> Optional[float]:
    """
    Minimum Night Flow robusto: p05 da série noturna.

    Usa o percentil 5 em vez do mínimo absoluto para ignorar dropouts
    isolados de sensor (leitura zero espúria). Semanticamente é o "mínimo
    robusto" — consumo noturno quase mínimo, excluindo os 5% mais baixos.

    Deve ser chamado APENAS para o período "night"; o orquestrador
    compute_baseline_row cuida disso.

    Args:
        values: série de vazão do período noturno.

    Returns:
        p05 da série; None se lista vazia.
    """
    if not values:
        return None
    return percentile(values, 5)


# ---------------------------------------------------------------------------
# 4. Limites comportamentais (percentis — sem absolutos)
# ---------------------------------------------------------------------------

def behavioral_bounds(stats: dict[str, Any]) -> dict[str, Optional[float]]:
    """
    Deriva os limites normal_low/high e anomaly_low/high a partir dos percentis
    da própria instalação.

    Nenhum valor absoluto (L/h) é usado aqui. Os limites refletem apenas o
    comportamento histórico do canal.

    Lógica:
        normal_low  = p10   (baixo normal)
        normal_high = p90   (alto normal)
        IQR = p75 - p25
        anomaly_high = max(p95, p75 + 1.5 × IQR)   ← generoso, evita falso positivo
        anomaly_low  = max(0.0, min(p05, p25 - 1.5 × IQR))  ← vazão ≥ 0

    Args:
        stats: dicionário retornado por compute_statistics.

    Returns:
        Dicionário com chaves normal_low, normal_high, anomaly_low, anomaly_high.
        Todos None se a série estava vazia (percentis None).
    """
    p05 = stats.get("p05")
    p10 = stats.get("p10")
    p25 = stats.get("p25")
    p75 = stats.get("p75")
    p90 = stats.get("p90")
    p95 = stats.get("p95")

    if any(v is None for v in (p05, p10, p25, p75, p90, p95)):
        return {
            "normal_low": None,
            "normal_high": None,
            "anomaly_low": None,
            "anomaly_high": None,
        }

    iqr = p75 - p25  # type: ignore[operator]
    anomaly_high = max(p95, p75 + ANOMALY_IQR_K * iqr)  # type: ignore[operator]
    anomaly_low = max(0.0, min(p05, p25 - ANOMALY_IQR_K * iqr))  # type: ignore[operator]

    return {
        "normal_low": p10,
        "normal_high": p90,
        "anomaly_low": anomaly_low,
        "anomaly_high": anomaly_high,
    }


def typical_variation_per_hour(
    values: list[float],
    timestamps: list[datetime],
) -> Optional[float]:
    """
    Variação típica por hora: mediana de |Δvalue| / Δhoras entre pontos
    consecutivos.

    Mediana é robusta a spikes de leitura. Captura a "agitação" normal do
    canal sem depender de magnitude absoluta.

    Args:
        values:     série de valores alinhada com timestamps.
        timestamps: datetimes correspondentes.

    Returns:
        Mediana das variações horárias; None se < 2 pontos ou todos Δt <= 0.
    """
    if len(values) < 2 or len(values) != len(timestamps):
        return None

    rates: list[float] = []
    for i in range(1, len(values)):
        dt_hours = (timestamps[i] - timestamps[i - 1]).total_seconds() / 3600.0
        if dt_hours <= 0:
            continue
        delta = abs(values[i] - values[i - 1])
        rates.append(delta / dt_hours)

    return statistics.median(rates) if rates else None


# ---------------------------------------------------------------------------
# 5. Classificações
# ---------------------------------------------------------------------------

def classify_profile(
    zero_ratio: float,
    near_zero_ratio: float,
    sample_count: int,
) -> Optional[str]:
    """
    Classifica o perfil de consumo com base em FORMATO (proporções), nunca
    em magnitude absoluta.

    Valores possíveis: "inactive", "continuous", "intermittent", "variable".

    Args:
        zero_ratio:      fração de pontos com vazão ≈ 0.
        near_zero_ratio: fração de pontos em repouso (v <= NEAR_ZERO_FLOW_LPH).
        sample_count:    tamanho da série.

    Returns:
        String de perfil ou None se sample_count == 0.
    """
    if sample_count == 0:
        return None
    if zero_ratio >= PROFILE_INACTIVE_ZERO_RATIO:
        return "inactive"
    if near_zero_ratio <= PROFILE_CONTINUOUS_REST_RATIO:
        return "continuous"
    if near_zero_ratio >= PROFILE_INTERMITTENT_REST_RATIO:
        return "intermittent"
    return "variable"


def classify_confidence(
    window_days: int,
    sample_count: int,
    expected_samples: Optional[int],
    coverage_pct: float,
) -> str:
    """
    Classifica a confiança estatística do baseline (relatório seção 10.6).

    Conservador: prefere nível menor se cobertura ou amostragem forem duvidosas.

    Níveis: "low" < "medium" < "high" < "consolidated".

    Lógica:
        Se expected_samples > 0 e coverage_pct == 0 (inconsistente), recomputa
        coverage_pct = 100 × sample_count / expected_samples.
        effective_days = window_days × coverage_pct / 100
        Se sample_count < MIN_SAMPLES_FOR_CONFIDENCE → "low"
        Se effective_days < 8  → "low"
        Se effective_days < 15 → "medium"
        Se effective_days < 30 → "high"
        Senão → "consolidated"

    Args:
        window_days:      duração total da janela em dias.
        sample_count:     número real de amostras no período.
        expected_samples: número teórico de amostras (None se desconhecido).
        coverage_pct:     cobertura calculada (0–100). Pode ser 0 se ainda não
                          calculada pelo chamador.

    Returns:
        String de confiança.
    """
    # Recomputa coverage_pct de forma defensiva quando inconsistente.
    effective_coverage = coverage_pct
    if expected_samples and expected_samples > 0 and coverage_pct <= 0:
        effective_coverage = 100.0 * sample_count / expected_samples

    effective_days = window_days * effective_coverage / 100.0

    if sample_count < MIN_SAMPLES_FOR_CONFIDENCE:
        return "low"
    if effective_days < CONF_MEDIUM_DAYS:
        return "low"
    if effective_days < CONF_HIGH_DAYS:
        return "medium"
    if effective_days < CONF_CONSOLIDATED_DAYS:
        return "high"
    return "consolidated"


# ---------------------------------------------------------------------------
# 6. Orquestrador
# ---------------------------------------------------------------------------

def compute_baseline_row(
    values: list[float],
    timestamps: list[datetime],
    *,
    metric: str,
    period: str,
    window_days: int,
    expected_samples: Optional[int] = None,
    coverage_pct: float,
    near_zero_threshold: float = NEAR_ZERO_FLOW_LPH,
) -> dict[str, Any]:
    """
    Computa todos os campos calculados de uma linha de installation_behavior_baselines.

    Orquestra os helpers acima; é a função que o behavior_baseline_worker (Fase 3)
    chamará para cada (installation, channel_role, metric_name, period_type).

    Args:
        values:              lista de float — valores da série já filtrada para
                             o período. Pode ser vazia (instalação nova).
        timestamps:          lista de datetime alinhada com values (UTC ou BRT;
                             usada só para Δt em runs e variação horária).
        metric:              nome da métrica (ex.: "flow2_lph") — usado apenas
                             para decidir se minimum_night_flow se aplica.
        period:              tipo do período (ex.: "night") — "night" ativa MNF.
        window_days:         duração da janela em dias (default 30).
        expected_samples:    nº teórico de leituras na janela (ex.: 2880).
        coverage_pct:        cobertura da janela (0–100).
        near_zero_threshold: limiar de repouso em L/h (default NEAR_ZERO_FLOW_LPH).

    Returns:
        Dicionário com exatamente as chaves dos campos calculados da tabela:
            mean, std, min, max, p05, p10, p25, p50, p75, p90, p95,
            zero_ratio, near_zero_ratio,
            longest_zero_minutes, typical_zero_minutes,
            longest_continuous_flow_minutes, typical_continuous_flow_minutes,
            minimum_night_flow,
            normal_low, normal_high, anomaly_low, anomaly_high,
            typical_variation_per_hour,
            profile_type, confidence,
            coverage_pct, window_days, expected_samples, sample_count.

        NÃO inclui: installation_id, channel_role, metric_name, period_type,
        window_start_at, window_end_at, computed_at — o worker preenche esses.

    Robusto a values vazio: retorna linha com confidence="low" e zeros/None
    sem estourar.
    """
    sample_count = len(values)

    # ── Estatísticas descritivas ─────────────────────────────────────────────
    stats = compute_statistics(values)

    # ── Repouso e fluxo contínuo ─────────────────────────────────────────────
    zr, nzr = zero_ratios(values, near_zero_threshold)
    longest_rest, typical_rest = rest_run_minutes(values, timestamps, near_zero_threshold)
    longest_flow, typical_flow = flow_run_minutes(values, timestamps, near_zero_threshold)

    # Minimum Night Flow: só faz sentido para o período noturno.
    mnf: Optional[float] = (
        minimum_night_flow(values) if period == "night" else None
    )

    # ── Limites comportamentais ──────────────────────────────────────────────
    bounds = behavioral_bounds(stats)

    # ── Variação típica horária ──────────────────────────────────────────────
    typ_var = typical_variation_per_hour(values, timestamps)

    # ── Classificações ───────────────────────────────────────────────────────
    profile = classify_profile(zr, nzr, sample_count)
    conf = classify_confidence(window_days, sample_count, expected_samples, coverage_pct)

    return {
        # Estatísticas
        "mean":   stats["mean"],
        "std":    stats["std"],
        "min":    stats["min"],
        "max":    stats["max"],
        "p05":    stats["p05"],
        "p10":    stats["p10"],
        "p25":    stats["p25"],
        "p50":    stats["p50"],
        "p75":    stats["p75"],
        "p90":    stats["p90"],
        "p95":    stats["p95"],
        # Padrões de repouso e fluxo
        "zero_ratio":                       zr,
        "near_zero_ratio":                  nzr,
        "longest_zero_minutes":             longest_rest,
        "typical_zero_minutes":             typical_rest,
        "longest_continuous_flow_minutes":  longest_flow,
        "typical_continuous_flow_minutes":  typical_flow,
        "minimum_night_flow":               mnf,
        # Limites comportamentais
        "normal_low":                       bounds["normal_low"],
        "normal_high":                      bounds["normal_high"],
        "anomaly_low":                      bounds["anomaly_low"],
        "anomaly_high":                     bounds["anomaly_high"],
        "typical_variation_per_hour":       typ_var,
        # Classificação
        "profile_type":                     profile,
        "confidence":                       conf,
        # Cobertura e janela
        "coverage_pct":     coverage_pct,
        "window_days":      window_days,
        "expected_samples": expected_samples,
        "sample_count":     sample_count,
    }
