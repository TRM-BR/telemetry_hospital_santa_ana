"""Vazão líquida derivada de série de nível (sensor analógico).

Funções puras, sem DB. Usadas read-time em dashboard.py.

Convenção de sinal: positivo = enchendo, negativo = consumindo.
Capacidade padrão do Hospital Santa Ana: 40.000 L/grupo (4 caixas × 10.000 L).
"""
from __future__ import annotations

import bisect
from datetime import datetime, timedelta, timezone
from typing import Sequence

# (epoch_ms, value)
Point = tuple[int, float]


def volume_l(level_pct: float, capacity_l: float) -> float:
    return level_pct / 100.0 * capacity_l


def net_flow_series(
    points: Sequence[Point],
    capacity_l: float,
    window_hours: float = 1.0,
) -> list[Point]:
    """Vazão líquida (L/h) com janela deslizante.

    Para cada ponto i, encontra o ponto j mais recente tal que
    ts[j] <= ts[i] - window_hours. flow = ΔVolume / Δt_h (com sinal).
    Pontos sem j na janela são ignorados.
    """
    if not points:
        return []

    window_ms = int(window_hours * 3_600_000)
    ts = [p[0] for p in points]
    result: list[Point] = []

    for i in range(1, len(points)):
        t_i, v_i = points[i]
        threshold = t_i - window_ms
        j = bisect.bisect_right(ts, threshold, 0, i) - 1
        if j < 0:
            continue
        t_j, v_j = points[j]
        delta_h = (t_i - t_j) / 3_600_000.0
        if delta_h <= 0:
            continue
        flow = (volume_l(v_i, capacity_l) - volume_l(v_j, capacity_l)) / delta_h
        result.append((t_i, round(flow, 1)))

    return result


def net_flow_hourly(
    points: Sequence[Point],
    capacity_l: float,
    tz: str,
) -> list[Point]:
    """Vazão líquida por balde horário (litros com sinal), timezone-aware.

    Retorna (boundary_end_ms, delta_volume_l) para cada hora completa.
    Hora sem cobertura de pontos em ambas as extremidades é omitida.
    """
    if len(points) < 2:
        return []

    import zoneinfo

    local_tz = zoneinfo.ZoneInfo(tz)
    ts = [p[0] for p in points]

    def last_vol_at(ms: int) -> float | None:
        idx = bisect.bisect_right(ts, ms) - 1
        if idx < 0:
            return None
        return volume_l(points[idx][1], capacity_l)

    t_start_ms, t_end_ms = ts[0], ts[-1]
    dt_start = datetime.fromtimestamp(t_start_ms / 1000.0, tz=timezone.utc).astimezone(local_tz)
    dt_end = datetime.fromtimestamp(t_end_ms / 1000.0, tz=timezone.utc).astimezone(local_tz)

    h0 = dt_start.replace(minute=0, second=0, microsecond=0)
    h_end = dt_end.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    boundaries: list[datetime] = []
    h = h0
    while h <= h_end:
        boundaries.append(h)
        h += timedelta(hours=1)

    result: list[Point] = []
    for i in range(1, len(boundaries)):
        b0_ms = int(boundaries[i - 1].timestamp() * 1000)
        b1_ms = int(boundaries[i].timestamp() * 1000)
        vol0 = last_vol_at(b0_ms)
        vol1 = last_vol_at(b1_ms)
        if vol0 is None or vol1 is None:
            continue
        result.append((b1_ms, round(vol1 - vol0, 1)))

    return result
