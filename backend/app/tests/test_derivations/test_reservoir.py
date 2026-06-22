"""Testes unitários para reservoir.py — cálculo nominal de nível/volume/%.

Critérios de aceite do plano:
  idc=9.274  → nivel_m≈1.318, volume_tank≈8000, percentual≈80,
               faltante_tank≈2000, volume_group≈32000, faltante_group≈8000,
               altura_faltante≈0.330
  idc=10.592 → nivel_m=1.648, volume_tank=10000, percentual=100, faltante_tank=0
  idc>full   → clamp: volume=10000, percentual=100, faltante=0
  idc<4mA    → level_m<0 → clamp 0
"""
from __future__ import annotations

import math
import pytest

from app.processing.derivations.reservoir import (
    ReservoirConfig,
    tank_volume_l,
    tank_percent,
    group_volume_l,
    altura_faltante_m,
    readout,
)
from app.processing.derivations.flow_from_level import consumption_series

# Config padrão Hospital Santa Ana
CFG = ReservoirConfig(
    tank_capacity_l=10_000.0,
    tank_count=4,
    group_capacity_l=40_000.0,
    height_reference_m=1.648,
    diameter_base_m=2.78,
)

# idc=9.274 mA → (9.274-4)/4 = 1.3185 m
LEVEL_TYPICAL = (9.274 - 4.0) / 4.0   # ≈ 1.3185
LEVEL_FULL    = (10.592 - 4.0) / 4.0  # = 1.648


# ── tank_volume_l ────────────────────────────────────────────────────────────

def test_tank_volume_typical():
    v = tank_volume_l(LEVEL_TYPICAL, CFG)
    assert abs(v - 8000.0) < 10, f"expected ~8000, got {v}"


def test_tank_volume_full():
    v = tank_volume_l(LEVEL_FULL, CFG)
    assert abs(v - 10_000.0) < 1


def test_tank_volume_clamp_above():
    v = tank_volume_l(2.5, CFG)  # acima de 1.648m
    assert v == 10_000.0


def test_tank_volume_clamp_below():
    v = tank_volume_l(-0.5, CFG)  # level negativo
    assert v == 0.0


# ── tank_percent ─────────────────────────────────────────────────────────────

def test_tank_percent_typical():
    p = tank_percent(LEVEL_TYPICAL, CFG)
    assert abs(p - 80.0) < 0.1, f"expected ~80%, got {p}"


def test_tank_percent_full():
    p = tank_percent(LEVEL_FULL, CFG)
    assert abs(p - 100.0) < 0.01


def test_tank_percent_clamp_above():
    p = tank_percent(3.0, CFG)
    assert p == 100.0


def test_tank_percent_zero():
    p = tank_percent(0.0, CFG)
    assert p == 0.0


# ── group_volume_l ───────────────────────────────────────────────────────────

def test_group_volume_typical():
    gv = group_volume_l(LEVEL_TYPICAL, CFG)
    assert abs(gv - 32_000.0) < 40, f"expected ~32000, got {gv}"


def test_group_volume_full():
    gv = group_volume_l(LEVEL_FULL, CFG)
    assert abs(gv - 40_000.0) < 1


def test_group_volume_clamp_above():
    gv = group_volume_l(9.0, CFG)
    assert gv == 40_000.0


# ── altura_faltante_m ────────────────────────────────────────────────────────

def test_altura_faltante_typical():
    af = altura_faltante_m(LEVEL_TYPICAL, CFG)
    assert abs(af - (1.648 - LEVEL_TYPICAL)) < 0.001


def test_altura_faltante_full():
    af = altura_faltante_m(LEVEL_FULL, CFG)
    assert af == 0.0


def test_altura_faltante_above_ref():
    af = altura_faltante_m(2.0, CFG)
    assert af == 0.0


# ── readout ──────────────────────────────────────────────────────────────────

def test_readout_typical():
    ro = readout(LEVEL_TYPICAL, CFG)
    assert abs(ro["nivel_m"] - LEVEL_TYPICAL) < 0.001
    assert abs(ro["percentual"] - 80.0) < 0.1
    assert abs(ro["volume_tank_l"] - 8000.0) < 10
    assert abs(ro["faltante_tank_l"] - 2000.0) < 10
    assert abs(ro["volume_group_l"] - 32_000.0) < 40
    assert abs(ro["faltante_group_l"] - 8_000.0) < 40
    assert abs(ro["altura_faltante_m"] - (1.648 - LEVEL_TYPICAL)) < 0.001


def test_readout_full():
    ro = readout(LEVEL_FULL, CFG)
    assert ro["percentual"] == pytest.approx(100.0, abs=0.01)
    assert ro["volume_tank_l"] == pytest.approx(10_000.0, abs=1.0)
    assert ro["faltante_tank_l"] == 0.0
    assert ro["faltante_group_l"] == 0.0
    assert ro["altura_faltante_m"] == 0.0


def test_readout_clamp_above():
    ro = readout(3.0, CFG)
    assert ro["percentual"] == 100.0
    assert ro["volume_tank_l"] == 10_000.0
    assert ro["faltante_tank_l"] == 0.0


# ── consumption_series coerência com volume nominal ──────────────────────────

def test_consumption_lph_matches_delta_volume():
    """Consumo em L/h deve bater com ΔLitros/Δt da série nominal."""
    # level_pct points derived from tank_percent of nominal level
    # Level caindo de 1.4m para 1.2m em 1h = delta_vol = (1.4-1.2)/1.648 * 10000 * 4
    t0 = 0
    t1 = 3_600_000  # 1h em ms

    lvl0 = 1.4
    lvl1 = 1.2
    pct0 = tank_percent(lvl0, CFG)
    pct1 = tank_percent(lvl1, CFG)
    gvol0 = group_volume_l(lvl0, CFG)
    gvol1 = group_volume_l(lvl1, CFG)

    pts = [(t0, pct0), (t1, pct1)]
    result = consumption_series(pts, CFG.group_capacity_l)

    assert len(result) == 1
    t_out, v_out = result[0]
    expected_consumption = gvol0 - gvol1  # L consumidos em 1h = L/h
    assert abs(v_out - expected_consumption) < 1.0, (
        f"expected ~{expected_consumption:.1f} L/h, got {v_out:.1f}"
    )
