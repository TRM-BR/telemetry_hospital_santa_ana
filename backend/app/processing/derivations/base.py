"""
app/processing/derivations/base.py — Tipos base para derivations.

Calibration: parâmetros de calibração de um dispositivo.
  Colunas espelham a tabela calibrations após migration 0003:
    ref_min_mca — pressão MCA que corresponde a nível 0% (reservatório vazio)
    ref_max_mca — pressão MCA que corresponde a nível 100% (reservatório cheio)
  Ambas são NULL quando ainda não há calibração registrada → level_* não é derivado.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Calibration:
    """
    Parâmetros de calibração ativos para um dispositivo.

    ref_min_mca : pressão MCA correspondente a nível 0% (tanque vazio).
                  NULL → não é possível calcular level_pct / level_m.
    ref_max_mca : pressão MCA correspondente a nível 100% (tanque cheio).
                  NULL → idem.
    """
    ref_min_mca: Optional[float] = None
    ref_max_mca: Optional[float] = None
