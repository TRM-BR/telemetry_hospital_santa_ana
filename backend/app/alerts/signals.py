"""
app/alerts/signals.py — Helpers de série para os detectores de alerta.

Funções puras e stateless que operam sobre listas de SeriesPoint.
Nenhuma dependência com banco ou workers.

Contrato central:
  - sustained(...) → verifica se uma condição vale em múltiplas leituras
    (nunca numa série de apenas 1 ponto de ruído).
  - robust_high(...)  → valor robusto de pico (p90 da janela, não o máximo).
  - smoothed_slope(...) → tendência via regressão sobre série suavizada.
"""
from __future__ import annotations

import statistics
from collections.abc import Callable
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Importação do tipo SeriesPoint — evita import circular com alert_worker.
# Em produção, alert_worker importa desta camada, não o contrário.
# ---------------------------------------------------------------------------
# SeriesPoint é um simples dataclass com campos .ts (datetime) e .value (float).
# Tipagem: usa typing.Any para desacoplar completamente.
from typing import Any

SeriesPoint = Any  # alias local — duck-typing: precisa de .ts e .value

# Repouso: vazão ≤ este valor é "em repouso" (centralizado em behavior.py).
# Copiado aqui para não criar importação circular.
_REST_LPH: float = 1.0


# ---------------------------------------------------------------------------
# 1. Persistência — coração da cura dos falsos positivos
# ---------------------------------------------------------------------------

def sustained(
    series: list[SeriesPoint],
    predicate: Callable[[float], bool],
    *,
    min_readings: int = 3,
    window_minutes: float = 30.0,
    coverage_frac: float = 0.75,
    now: datetime | None = None,
) -> bool:
    """
    Retorna True se `predicate` vale de forma sustentada nos últimos
    `window_minutes` minutos, com pelo menos `min_readings` pontos e
    cobertura de `coverage_frac` da janela.

    Mata falsos positivos de ruído: um pico isolado não passa.

    Args:
        series:          série ordenada ascendentemente por .ts.
        predicate:       condição sobre o valor do ponto (ex.: lambda v: v > 12.0).
        min_readings:    mínimo de pontos na janela (padrão 3).
        window_minutes:  tamanho da janela (padrão 30 min).
        coverage_frac:   fração mínima dos pontos da janela onde predicate é True.
        now:             instante de referência (padrão: .ts do último ponto).

    Returns:
        True apenas se todos os requisitos são atendidos simultaneamente.
    """
    if not series:
        return False

    ref = now if now is not None else series[-1].ts
    cutoff = ref.timestamp() - window_minutes * 60.0
    window = [p for p in series if p.ts.timestamp() >= cutoff]

    if len(window) < min_readings:
        return False

    positive = sum(1 for p in window if predicate(p.value))
    return (positive / len(window)) >= coverage_frac


def sustained_below(
    series: list[SeriesPoint],
    threshold: float,
    *,
    min_readings: int = 3,
    window_minutes: float = 30.0,
    coverage_frac: float = 0.75,
    now: datetime | None = None,
) -> bool:
    """Atalho: sustained com predicate = value < threshold."""
    return sustained(
        series, lambda v: v < threshold,
        min_readings=min_readings,
        window_minutes=window_minutes,
        coverage_frac=coverage_frac,
        now=now,
    )


def sustained_above(
    series: list[SeriesPoint],
    threshold: float,
    *,
    min_readings: int = 3,
    window_minutes: float = 30.0,
    coverage_frac: float = 0.75,
    now: datetime | None = None,
) -> bool:
    """Atalho: sustained com predicate = value > threshold."""
    return sustained(
        series, lambda v: v > threshold,
        min_readings=min_readings,
        window_minutes=window_minutes,
        coverage_frac=coverage_frac,
        now=now,
    )


# ---------------------------------------------------------------------------
# 2. Valor robusto de pico (substitui max isolado)
# ---------------------------------------------------------------------------

def robust_high(
    series: list[SeriesPoint],
    percentile: float = 90.0,
) -> float | None:
    """
    Valor robusto de pico: percentil da janela (padrão p90).

    Substitui o máximo isolado (max point), que é frágil a spikes de sensor.
    Um valor aparece como pico só se ~10% dos pontos da janela já estão naquela
    faixa — filtra sozinho o ruído aleatório.

    Args:
        series:     pontos da janela (já filtrados por tempo pelo chamador).
        percentile: percentil desejado (0–100).

    Returns:
        Valor do percentil; None se lista vazia.
    """
    if not series:
        return None
    vals = sorted(p.value for p in series)
    n = len(vals)
    if n == 1:
        return vals[0]
    rank = percentile / 100.0 * (n - 1)
    lo = int(rank)
    hi = lo + 1
    frac = rank - lo
    if hi >= n:
        return vals[-1]
    return vals[lo] + frac * (vals[hi] - vals[lo])


# ---------------------------------------------------------------------------
# 3. Inclinação suavizada (substitui diferença de pontas)
# ---------------------------------------------------------------------------

def smoothed_slope(
    series: list[SeriesPoint],
    lookback_hours: float = 1.5,
    now: datetime | None = None,
) -> float | None:
    """
    Inclinação (unidade/hora) via regressão linear sobre série suavizada.

    A suavização (mediana de janelas de 3 pontos consecutivos) elimina
    spikes isolados de sensor antes da regressão. Isso cura o falso positivo
    de "queda" calculada entre um pico inicial e um vale final — a regressão
    sobre a série suavizada reflete a tendência real.

    Positivo = subindo; negativo = caindo.
    None quando há pontos insuficientes (< 3 após suavização).

    Args:
        series:        série ordenada por .ts, ascendentemente.
        lookback_hours: janela de lookback.
        now:           instante de referência (padrão: último ponto da série).
    """
    if not series:
        return None
    ref = now if now is not None else series[-1].ts
    cutoff = ref.timestamp() - lookback_hours * 3600.0
    window = [p for p in series if p.ts.timestamp() >= cutoff]
    if len(window) < 3:
        return None

    # Suavização: mediana de vizinhos disponíveis (janela adaptativa nas bordas).
    # Inclui o ponto de borda na suavização com seus vizinhos imediatos,
    # eliminando spikes isolados nas extremidades da série.
    smoothed: list[tuple[float, float]] = []  # (ts_seconds, value)
    for i in range(len(window)):
        lo = max(0, i - 1)
        hi = min(len(window) - 1, i + 1)
        ts_s = window[i].ts.timestamp()
        med = statistics.median([window[j].value for j in range(lo, hi + 1)])
        smoothed.append((ts_s, med))

    if len(smoothed) < 3:
        return None

    # Regressão linear sobre (tempo_horas, valor).
    ts_ref = smoothed[0][0]
    xs = [(t - ts_ref) / 3600.0 for t, _ in smoothed]
    ys = [v for _, v in smoothed]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0.0:
        return None
    return num / den  # positivo = subindo


def drop_per_hour(
    series: list[SeriesPoint],
    lookback_hours: float = 1.5,
    now: datetime | None = None,
) -> float | None:
    """
    Queda (units/hora), baseada em smoothed_slope.
    Positivo = caindo; None se série insuficiente ou subindo.
    """
    slope = smoothed_slope(series, lookback_hours=lookback_hours, now=now)
    if slope is None:
        return None
    return -slope if slope < 0 else None


# ---------------------------------------------------------------------------
# 4. Helpers de janela e série
# ---------------------------------------------------------------------------

def window_points(
    series: list[SeriesPoint],
    minutes: float,
    now: datetime,
) -> list[SeriesPoint]:
    """Pontos da série nos últimos `minutes` minutos antes de `now`."""
    cutoff = now.timestamp() - minutes * 60.0
    return [p for p in series if p.ts.timestamp() >= cutoff]


def window_mean(
    series: list[SeriesPoint],
    minutes: float,
    now: datetime,
) -> float | None:
    """Média dos valores nos últimos `minutes` minutos. None se janela vazia."""
    pts = window_points(series, minutes, now)
    if not pts:
        return None
    return sum(p.value for p in pts) / len(pts)


def nights_without_rest(
    series: list[SeriesPoint],
    rest_threshold: float = _REST_LPH,
    min_night_points: int = 3,
    lookback_days: int = 7,
    now: datetime | None = None,
) -> int:
    """
    Conta quantas das últimas `lookback_days` noites não tiveram nenhum ponto
    em repouso (v <= rest_threshold).

    Noite = 00h–06h BRT (UTC-3).
    Usado por detect_no_rest_overnight para detectar vazamento noturno.

    Returns:
        Número de noites consecutivas (das mais recentes) sem repouso.
        0 se a noite mais recente teve repouso.
    """
    from datetime import timezone
    brt = timezone(timedelta(hours=-3))

    ref = now if now is not None else (series[-1].ts if series else None)
    if ref is None or not series:
        return 0

    ref_brt = ref.astimezone(brt)
    consecutive = 0

    for day_offset in range(lookback_days):
        # Início e fim da janela noturna (00h–06h BRT) de `day_offset` dias atrás.
        night_date = (ref_brt - timedelta(days=day_offset)).date()
        night_start = datetime(
            night_date.year, night_date.month, night_date.day,
            0, 0, 0, tzinfo=brt,
        )
        night_end = night_start + timedelta(hours=6)

        night_pts = [
            p for p in series
            if night_start.timestamp() <= p.ts.timestamp() < night_end.timestamp()
        ]

        if len(night_pts) < min_night_points:
            # Sem dados suficientes para esta noite — para a contagem.
            break

        had_rest = any(p.value <= rest_threshold for p in night_pts)
        if not had_rest:
            consecutive += 1
        else:
            break  # noite com repouso interrompe a contagem consecutiva

    return consecutive


def days_since_last_rest(
    series: list[SeriesPoint],
    rest_threshold: float = _REST_LPH,
    lookback_days: int = 30,
    now: datetime | None = None,
) -> Optional[int]:
    """
    Dias inteiros desde a última vez que a vazão caiu a <= rest_threshold,
    em QUALQUER horário do dia.

    Returns:
        int >= 0 → dias desde a última zeragem (0 se zerou nas últimas 24h).
        None    → nenhuma zeragem encontrada na janela de lookback.
    """
    if not series:
        return None
    ref = now if now is not None else series[-1].ts
    cutoff_ts = ref.timestamp() - lookback_days * 86400.0

    for p in reversed(series):
        if p.ts.timestamp() < cutoff_ts:
            break
        if p.value <= rest_threshold:
            delta_s = ref.timestamp() - p.ts.timestamp()
            return max(0, int(delta_s // 86400))
    return None


def night_by_night_summary(
    series: list[SeriesPoint],
    rest_threshold: float = _REST_LPH,
    lookback_days: int = 30,
    now: datetime | None = None,
) -> list[dict]:
    """
    Resumo noite-a-noite (00–06h BRT) das últimas `lookback_days` noites.

    Retorna uma lista de dicts (mais recentes primeiro), uma entrada por noite:
        { "noite": "YYYY-MM-DD", "min": float, "mean": float,
          "pontos": int, "repouso": bool }

    Para quando a janela de dados se esgota (< 3 pontos numa noite).
    Mesmos critérios de `nights_without_rest`.
    """
    from datetime import timezone
    brt = timezone(timedelta(hours=-3))

    ref = now if now is not None else (series[-1].ts if series else None)
    if ref is None or not series:
        return []

    ref_brt = ref.astimezone(brt)
    result = []

    for day_offset in range(lookback_days):
        night_date = (ref_brt - timedelta(days=day_offset)).date()
        night_start = datetime(
            night_date.year, night_date.month, night_date.day,
            0, 0, 0, tzinfo=brt,
        )
        night_end = night_start + timedelta(hours=6)

        night_pts = [
            p for p in series
            if night_start.timestamp() <= p.ts.timestamp() < night_end.timestamp()
        ]

        if len(night_pts) < 3:
            break

        vals = [p.value for p in night_pts]
        result.append({
            "noite":   night_date.isoformat(),
            "min":     round(min(vals), 2),
            "mean":    round(sum(vals) / len(vals), 2),
            "pontos":  len(vals),
            "repouso": any(v <= rest_threshold for v in vals),
        })

    return result


def max_continuous_flow_minutes(
    series: list[SeriesPoint],
    rest_threshold: float = _REST_LPH,
    lookback_hours: float = 48.0,
    now: datetime | None = None,
) -> float:
    """
    Duração máxima (minutos) de fluxo contínuo sem repouso nos últimos
    `lookback_hours` horas.

    Usado para detectar consumo ininterrupto por longa janela de tempo.

    Returns:
        Duração em minutos do run mais longo acima de rest_threshold.
        0.0 se nenhum run encontrado ou série vazia.
    """
    if not series:
        return 0.0
    ref = now if now is not None else series[-1].ts
    cutoff = ref.timestamp() - lookback_hours * 3600.0
    window = [p for p in series if p.ts.timestamp() >= cutoff]
    if not window:
        return 0.0

    max_run = 0.0
    run_start: int | None = None

    for i, p in enumerate(window):
        if p.value > rest_threshold:
            if run_start is None:
                run_start = i
        else:
            if run_start is not None:
                dur = (window[i - 1].ts.timestamp() - window[run_start].ts.timestamp()) / 60.0
                max_run = max(max_run, dur)
                run_start = None

    if run_start is not None:
        dur = (window[-1].ts.timestamp() - window[run_start].ts.timestamp()) / 60.0
        max_run = max(max_run, dur)

    return max_run
