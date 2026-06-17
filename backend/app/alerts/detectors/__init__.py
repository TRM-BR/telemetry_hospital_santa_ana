"""
app/alerts/detectors — Registry de detectores modulares.

Cada arquivo neste pacote implementa uma ou mais táticas de detecção
como funções puras registradas via @register_detector.

O registry é chamado por _run_pipeline em alert_worker.py após cada
tática legada ser migrada, fase a fase. Quando todas as táticas estiverem
aqui, _run_pipeline reduz a uma chamada de run_all_registered().

Uso:
    from app.alerts.detectors import run_all_registered
    results = run_all_registered(ctx, now, baseline_ok)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional

# Importação do tipo DetectorResult via duck-typing para desacoplar
# do módulo alert_worker (evitar import circular).
DetectorResultLike = Any

_REGISTRY: list[Callable[..., DetectorResultLike]] = []


def register_detector(fn: Callable[..., DetectorResultLike]) -> Callable:
    """Decorador que adiciona o detector à lista global de detectores."""
    _REGISTRY.append(fn)
    return fn


def run_all_registered(
    ctx: Any,
    now: datetime,
    baseline_ok: bool,
) -> list[DetectorResultLike]:
    """
    Executa todos os detectores registrados e retorna a lista de resultados.
    Compatível com a assinatura esperada por _run_pipeline.
    """
    results = []
    for fn in _REGISTRY:
        try:
            result = fn(ctx, now, baseline_ok)
            if isinstance(result, list):
                results.extend(result)
            else:
                results.append(result)
        except Exception:
            # Detector individual não deve derrubar o pipeline inteiro.
            pass
    return results
