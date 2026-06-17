"""
app/processing/derivations/flow_window.py — Vazão por janela deslizante de 1h.

Implementação Python fiel ao computeFlowSeries() de dashboardMetrics.ts.
Usa contadores acumulados (count_pulses / count2_pulses) de parsed_measurements
em vez da vazão instantânea de derived_metrics.flow_total_lph.

Por quê: o derive_worker calcula flow entre leituras *consecutivas*. Quando o
Dragino envia pacotes históricos (hist_index > 0), o Δt entre duas leituras
consecutivas pode ser segundos, produzindo spikes de 75+ L/h que não representam
consumo real. A janela de 1h sobre o contador acumulado elimina esses spikes.

Cada ponto de entrada produz exatamente um ponto de saída (mesmos índices),
igual ao comportamento do frontend — facilitando a soma de flow1+flow2.
"""
from __future__ import annotations

from datetime import datetime


def windowed_flow_series(
    points: list[tuple[datetime, float | None]],
    window_hours: float = 1.0,
    liter_per_pulse: float = 1.0,
) -> list[tuple[datetime, float]]:
    """
    Calcula vazão (L/h) via janela deslizante sobre contadores acumulados.

    Para cada ponto i, localiza o primeiro ponto j < i onde
    ts[j] <= ts[i] − window e computa:
        flow = max(0, (count[i] − count[j]) × lpp / Δt_horas)

    Pontos com count=None retornam flow=0 (mantendo alinhamento de índice).

    Args:
        points:            lista de (timestamp, contador_acumulado) em ordem ASC.
                           O contador pode ser None — o ponto é incluído com flow=0.
        window_hours:      largura da janela deslizante (padrão 1 h).
        liter_per_pulse:   litros por pulso (calibrations.flow_liter_per_pulse).

    Returns:
        Lista de (timestamp, flow_lph) do mesmo tamanho que `points`.
    """
    n = len(points)
    if n == 0:
        return []

    ts_epoch = [p[0].timestamp() for p in points]
    window_s = window_hours * 3600.0
    result: list[tuple[datetime, float]] = []

    for i in range(n):
        ts_i, count_i = points[i]

        if count_i is None:
            result.append((ts_i, 0.0))
            continue

        t_now = ts_epoch[i]
        cutoff = t_now - window_s

        # Busca o primeiro j < i com ts[j] <= cutoff (de trás pra frente)
        prev_idx = -1
        for j in range(i - 1, -1, -1):
            if ts_epoch[j] <= cutoff:
                prev_idx = j
                break

        if prev_idx == -1:
            result.append((ts_i, 0.0))
            continue

        _, count_prev = points[prev_idx]
        if count_prev is None:
            result.append((ts_i, 0.0))
            continue

        dt_hours = (t_now - ts_epoch[prev_idx]) / 3600.0
        if dt_hours <= 0:
            result.append((ts_i, 0.0))
            continue

        flow = max(0.0, (float(count_i) - float(count_prev)) * liter_per_pulse / dt_hours)
        result.append((ts_i, flow))

    return result
