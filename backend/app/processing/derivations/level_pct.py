"""
app/processing/derivations/level_pct.py — Cálculo de nível a partir de pressão.

Usa os pontos de referência da tabela calibrations (colunas em MCA após migration 0003):
  ref_min_mca — pressão correspondente a nível 0%
  ref_max_mca — pressão correspondente a nível 100%

Fórmula:
  span       = ref_max_mca - ref_min_mca
  level_pct  = clamp((pressure2_mca - ref_min_mca) / span * 100, 0, 100)
  level_m    = level_pct / 100 * level_max_m
"""
from __future__ import annotations

from typing import Optional


def calc_level_pct(
    pressure2_mca: Optional[float],
    ref_min_mca: Optional[float],
    ref_max_mca: Optional[float],
) -> Optional[float]:
    """
    Calcula o nível percentual.

    Args:
        pressure2_mca : pressão do sensor 2 já em MCA.
        ref_min_mca   : ponto de referência para 0% em MCA
                        (calibrations.ref_min_mca).
        ref_max_mca   : ponto de referência para 100% em MCA
                        (calibrations.ref_max_mca).

    Returns:
        Nível em % [0.0, 100.0], ou None se faltarem dados de calibração.
    """
    if pressure2_mca is None or ref_min_mca is None or ref_max_mca is None:
        return None

    span = ref_max_mca - ref_min_mca
    if span <= 0:
        return None

    raw = ((pressure2_mca - ref_min_mca) / span) * 100.0
    return max(0.0, min(100.0, raw))


def calc_level_m(level_pct: Optional[float], level_max_m: float) -> Optional[float]:
    """
    Converte nível percentual em metros.

    Args:
        level_pct   : saída de calc_level_pct (% em [0, 100]).
        level_max_m : altura total do reservatório em metros
                      (settings.level_max_m, default 3.0 m).

    Returns:
        Nível em metros, ou None se level_pct for None.
    """
    if level_pct is None:
        return None
    return (level_pct / 100.0) * level_max_m
