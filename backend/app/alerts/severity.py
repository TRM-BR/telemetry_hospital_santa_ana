"""
app/alerts/severity.py — Régua única de severidade por distância da faixa.

Regra monotônica, sem caminhos especiais por detector:
  - observed <= normal_high (ou >= normal_low)         → None  (dentro do normal)
  - mid_band < observed <= anomaly_high                → moderado
  - anomaly_high < observed < 2 × anomaly_high         → alto
  - observed >= 2 × anomaly_high                       → crítico
  Simétrico para o lado baixo (severity_from_band_low).

Não existe mais o nível "atenção" (atencao). Detectores que antes ficavam na
banda inferior (normal→mid) simplesmente não disparam (retornam None).
"""
from __future__ import annotations

import unicodedata
from typing import Optional

# ---------------------------------------------------------------------------
# Constantes exportadas
# ---------------------------------------------------------------------------

SEVERITY_ORDER: dict[str, int] = {
    "moderado": 0,
    "alto": 1,
    "critico": 2,
}

# Conjunto de severidades consideradas críticas para fins de NOTIFICAÇÃO
# (Telegram). Comparado já normalizado (sem acento, minúsculo, sem espaços).
# Não altera o pipeline de alertas — é só a régua da camada de notificação.
_CRITICAL_SEVERITIES: frozenset[str] = frozenset({"critico", "critical"})


def _normalize_severity(value: str) -> str:
    """Baixa caixa, remove espaços nas pontas e remove acentos (crítico → critico)."""
    nfkd = unicodedata.normalize("NFKD", value.strip().lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def is_critical_severity(severity: Optional[str]) -> bool:
    """
    True se a severidade representa um alerta crítico.

    Aceita variações legadas e em inglês: 'critico', 'crítico', 'CRITICO ',
    'critical'. Usado APENAS na camada de notificação Telegram/enfileiramento —
    não renomeia nem migra severidades existentes no banco.
    """
    if not severity:
        return False
    return _normalize_severity(severity) in _CRITICAL_SEVERITIES

# Múltiplo de anomaly_high a partir do qual a severidade sobe a crítico.
CRITICAL_MULTIPLIER: float = 2.0


# ---------------------------------------------------------------------------
# Helpers de severidade
# ---------------------------------------------------------------------------

def min_severity(a: str, b: str) -> str:
    """Retorna a severidade mais conservadora (menor nível) das duas."""
    return a if SEVERITY_ORDER.get(a, 0) <= SEVERITY_ORDER.get(b, 2) else b


def max_severity(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Retorna a severidade mais grave das duas. None se ambas forem None."""
    if a is None:
        return b
    if b is None:
        return a
    return a if SEVERITY_ORDER.get(a, 0) >= SEVERITY_ORDER.get(b, 0) else b


def severity_cap_by_confidence(confidence: str) -> str:
    """
    Teto de severidade permitido pela confiança do baseline.

        low          → máx. moderado
        medium       → máx. alto
        high         → máx. crítico
        consolidated → máx. crítico
    """
    return {
        "low":          "moderado",
        "medium":       "alto",
        "high":         "critico",
        "consolidated": "critico",
    }.get(confidence, "moderado")


# ---------------------------------------------------------------------------
# Régua unificada — lado alto
# ---------------------------------------------------------------------------

def severity_from_band(
    observed: float,
    normal_high: float,
    anomaly_high: float,
    confidence: str,
) -> tuple[str | None, str]:
    """
    Severidade para valor acima da faixa normal.

    Args:
        observed:     valor observado (sustentado — persistência garantida pelo chamador).
        normal_high:  teto da faixa normal (p90 do período).
        anomaly_high: teto da faixa anômala (max(p95, p75 + 1.5×IQR)).
        confidence:   confiança da baseline ("low", "medium", "high", "consolidated").

    Returns:
        (severity | None, reason_code)
        None → não alertar (dentro do normal ou banda inferior sem relevância).
    """
    if observed <= normal_high:
        return None, "within_normal"

    if anomaly_high <= normal_high:
        # Baseline degenerado: anomaly_high não sobrepõe normal_high.
        # Sem "atencao" — retorna None para não gerar ruído.
        return None, "degenerate_baseline"
    elif observed <= anomaly_high:
        mid = (normal_high + anomaly_high) / 2.0
        if observed <= mid:
            # Banda inferior (normal→mid): não dispara.
            return None, "band_lower_half"
        else:
            raw, reason = "moderado", "band_upper_half"
    elif observed >= CRITICAL_MULTIPLIER * anomaly_high:
        raw, reason = "critico", "at_least_2x_anomaly"
    else:
        raw, reason = "alto", "above_anomaly"

    capped = min_severity(raw, severity_cap_by_confidence(confidence))
    if capped != raw:
        reason += f"|capped_{confidence}"
    return capped, reason


# ---------------------------------------------------------------------------
# Régua unificada — lado baixo (perfil continuous)
# ---------------------------------------------------------------------------

def severity_from_band_low(
    observed: float,
    normal_low: float | None,
    anomaly_low: float | None,
    confidence: str,
) -> tuple[str | None, str]:
    """
    Severidade para valor abaixo da faixa normal (perfil continuous).

    anomaly_low < normal_low: quanto mais longe de normal_low, mais grave.
    Só faz sentido quando anomaly_low > 0 (fluxo com piso positivo esperado).

    Returns:
        (severity | None, reason_code)
        None → dentro do normal ou baseline inaplicável.
    """
    if anomaly_low is None or normal_low is None:
        return None, "incomplete_baseline"
    if anomaly_low <= 0:
        return None, "no_positive_floor"
    if observed >= normal_low:
        return None, "within_normal"

    if observed <= 0:
        raw, reason = "critico", "zero_flow_continuous"
    elif observed < anomaly_low:
        frac = observed / anomaly_low
        if frac <= 0.25:
            raw, reason = "alto", "far_below_anomaly_low"
        else:
            raw, reason = "moderado", "below_anomaly_low"
    else:
        # Entre anomaly_low e normal_low: sem "atencao" — não dispara.
        return None, "slightly_below_normal_low"

    capped = min_severity(raw, severity_cap_by_confidence(confidence))
    if capped != raw:
        reason += f"|capped_{confidence}"
    return capped, reason


# ---------------------------------------------------------------------------
# Régua por razão (magnitude relativa ao baseline)
# ---------------------------------------------------------------------------

def severity_from_ratio(
    ratio: float,
    *,
    moderado: float = 0.8,
    alto: float = 1.5,
    critico: float = 3.0,
) -> Optional[str]:
    """
    Severidade baseada em razão adimensional (observed / referência).

    Usada para comparar magnitude de um evento com o baseline da instalação.
    Exemplo: vazão noturna / normal_high_flow → quanto maior, mais grave.

    Retorna None se ratio < moderado (dentro da faixa aceitável).
    """
    if ratio >= critico:
        return "critico"
    if ratio >= alto:
        return "alto"
    if ratio >= moderado:
        return "moderado"
    return None
