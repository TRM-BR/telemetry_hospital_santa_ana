"""
app/processing/derivations/flow_lph.py — Cálculo de vazão (L/h e m³/h).

Fórmula (legado: scripts/derive_dragino_metrics.py:214-233):
    flow_lph = (delta_pulsos * litros_por_pulso) / delta_horas

Onde:
    delta_pulsos = count_agora - count_anterior  (descarta se negativo — overflow do contador)
    delta_horas  = (ts_agora - ts_anterior).total_seconds() / 3600

O Dragino SN50V3-NB acumula pulsos de caudalímetro. A vazão é calculada por
diff entre duas leituras consecutivas da mesma instalação.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional


def calc_flow(
    count_now: Optional[float],
    count_prev: Optional[float],
    ts_now: datetime,
    ts_prev: datetime,
    liter_per_pulse: float = 1.0,
) -> tuple[Optional[float], Optional[float]]:
    """
    Calcula vazão em L/h e m³/h a partir do diff de pulsos.

    Args:
        count_now       : contagem de pulsos atual.
        count_prev      : contagem de pulsos da leitura anterior.
        ts_now          : timestamp UTC da leitura atual.
        ts_prev         : timestamp UTC da leitura anterior.
        liter_per_pulse : litros por pulso (calibrations.flow_liter_per_pulse, default 1.0).

    Returns:
        (flow_lph, flow_m3h) — ambos None se não for possível calcular.
    """
    if count_now is None or count_prev is None:
        return None, None

    delta_pulses = count_now - count_prev
    if delta_pulses < 0:
        # Contador reiniciou (overflow) — descarta, não sinaliza erro
        return None, None

    dt_seconds = (ts_now - ts_prev).total_seconds()
    if dt_seconds <= 0:
        return None, None

    dt_hours = dt_seconds / 3600.0
    flow_lph = (delta_pulses * liter_per_pulse) / dt_hours
    flow_m3h = flow_lph / 1000.0
    return flow_lph, flow_m3h
