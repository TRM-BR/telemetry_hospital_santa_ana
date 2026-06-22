"""Cálculo nominal de nível/volume/percentual/faltante por reservatório.

Fortlev 10.000 L: diâmetro base 2,78 m, raio 1,39 m,
  área = π × 1,39² ≈ 6,067 m²,
  height_reference_m = 10000 / (6067 × 1000) ≈ 1,648 m.

Funções puras, sem DB. Usadas read-time em dashboard.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReservoirConfig:
    tank_capacity_l: float = 10_000.0
    tank_count: int = 4
    group_capacity_l: float = 40_000.0
    height_reference_m: float = 1.648
    diameter_base_m: float = 2.78


def tank_volume_l(level_m: float, cfg: ReservoirConfig) -> float:
    """Volume nominal da caixa individual, clampado 0..tank_capacity_l."""
    raw = (level_m / cfg.height_reference_m) * cfg.tank_capacity_l
    return max(0.0, min(cfg.tank_capacity_l, raw))


def tank_percent(level_m: float, cfg: ReservoirConfig) -> float:
    """% nominal da caixa individual, clampado 0..100."""
    return tank_volume_l(level_m, cfg) / cfg.tank_capacity_l * 100.0


def group_volume_l(level_m: float, cfg: ReservoirConfig) -> float:
    """Volume nominal do grupo (tank_count caixas equalizadas), clampado 0..group_capacity_l."""
    raw = tank_volume_l(level_m, cfg) * cfg.tank_count
    return max(0.0, min(cfg.group_capacity_l, raw))


def altura_faltante_m(level_m: float, cfg: ReservoirConfig) -> float:
    """Metros de coluna faltando para atingir a altura útil de referência."""
    return max(0.0, cfg.height_reference_m - level_m)


def readout(level_m: float, cfg: ReservoirConfig) -> dict:
    """Dict com todos os campos derivados de um level_m + config."""
    tvl = tank_volume_l(level_m, cfg)
    pct = tank_percent(level_m, cfg)
    gvl = group_volume_l(level_m, cfg)
    return {
        "nivel_m": round(level_m, 4),
        "percentual": round(pct, 2),
        "volume_tank_l": round(tvl, 1),
        "volume_group_l": round(gvl, 1),
        "faltante_tank_l": round(max(0.0, cfg.tank_capacity_l - tvl), 1),
        "faltante_group_l": round(max(0.0, cfg.group_capacity_l - gvl), 1),
        "altura_faltante_m": round(altura_faltante_m(level_m, cfg), 4),
    }
