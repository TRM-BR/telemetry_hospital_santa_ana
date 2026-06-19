"""
app/processing/derivations/analog_level.py — Conversão corrente → nível (DTN-200-FPS0).

Regra de 3 linear: 4–20 mA → level_min–level_max metros (escala do sensor).
  level_m   = level_min + (mA - 4)/(20 - 4) * (level_max - level_min)
  level_pct = (mA - 4)/(20 - 4) * 100      (fração da escala do sensor, 0–100%)

Fault detection: undercurrent (< fault_below_ma) e overrange (> fault_above_ma).
Quando há fault, level_m/level_pct NÃO são calculados — current_ma permanece visível.

Funções puras — sem dependência de banco ou config.
"""
from __future__ import annotations

from typing import Optional


def current_to_level(
    current_ma: float,
    profile: dict,
) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """
    Converte corrente (mA) em nível (m e %) por regra de 3 na escala do sensor.

    Args:
        current_ma:  leitura de corrente do transdutor (mA).
        profile:     dict com chaves do analog_profiles YAML:
                       current_min_ma, current_max_ma,
                       level_min_m, level_max_m,
                       fault_below_ma, fault_above_ma.

    Returns:
        (level_m, level_pct, fault_kind)
        - fault_kind: 'undercurrent' | 'overrange' | None
        - level_m / level_pct: None quando há fault
    """
    fault_below: float = float(profile.get("fault_below_ma", 4.0))
    fault_above: float = float(profile.get("fault_above_ma", 20.5))
    current_min: float = float(profile.get("current_min_ma", 4.0))
    current_max: float = float(profile.get("current_max_ma", 20.0))
    level_min: float = float(profile.get("level_min_m", 0.0))
    level_max: float = float(profile.get("level_max_m", 4.0))

    if current_ma < fault_below:
        return None, None, "undercurrent"

    if current_ma > fault_above:
        return None, None, "overrange"

    # Regra de 3 na faixa válida (4–20 mA → level_min–level_max m)
    span_current = current_max - current_min
    if span_current <= 0:
        return None, None, None

    ratio = (current_ma - current_min) / span_current
    level_m = level_min + ratio * (level_max - level_min)
    level_pct = max(0.0, min(100.0, ratio * 100.0))

    return level_m, level_pct, None
