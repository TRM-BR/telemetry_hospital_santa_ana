"""
app/processing/derivations/pressure_mca.py — Conversão pressão raw (kPa) → MCA.

Fórmula (legado: scripts/derive_dragino_metrics.py, constante PRESSURE_KPA_TO_MCA):
    pressure_mca = pressure_kpa * 0.1019716 * pressure_scale

O sensor Dragino SN50V3-NB entrega pressão em kPa (raw).
1 kPa = 0.1019716 MCA (metros de coluna d'água).
"""
from __future__ import annotations

from typing import Optional

# 1 kPa = 0.1019716 MCA
PRESSURE_KPA_TO_MCA: float = 0.1019716


def to_mca(pressure_kpa: Optional[float], scale: float = 1.0) -> Optional[float]:
    """
    Converte pressão em kPa para MCA (metros de coluna d'água).

    Args:
        pressure_kpa : leitura bruta do sensor em kPa (pressure_raw ou pressure2_raw).
        scale        : fator de escala do sensor (calibrations.pressure_scale, default 1.0).

    Returns:
        Pressão em MCA, ou None se a entrada for None.
    """
    if pressure_kpa is None:
        return None
    return pressure_kpa * PRESSURE_KPA_TO_MCA * scale
