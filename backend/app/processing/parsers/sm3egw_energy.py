"""
app/processing/parsers/sm3egw_energy.py — Parser para medidor SM-3EGW (IE Tecnologia).

Tópico MQTT: /param_energ
Profile: sm3egw_energy

O payload contém ~70 campos como strings; este parser extrai apenas
os 11 campos grifados + 2 deltas acordados (seção 4 do plano técnico).
Campos extras são ignorados silenciosamente.

Regras:
  - JSON válido obrigatório; inválido/vazio → EnergyParseResult(status="failed").
  - Todos os campos de medição são opcionais: ausente → None (nunca 0).
  - Valores chegam como string — converter; não-conversível → None (não quebra lote).
  - Negativos preservados (pt pode ser negativo em geração).
  - Sinal GSM: tenta rssi_gsm, cai para rssi_modem (varia por firmware).
    "-999" → None (sem sinal GSM).
  - Acumulados (ept_c, ept_g, eqt_g) → string decimal preservada para NUMERIC(18,3).
  - Normalização de nomes de delta: "deltaeptc" ≡ "delta_ept_c" (underscore-insensitive).
  - Sem timestamp no payload → collected_at_utc vem de received_at_utc (worker).
  - Nunca lança — erros → EnergyParseResult(status="failed").
"""
from __future__ import annotations

import json
from typing import Optional

from app.processing.parsers.base import EnergyParseResult, EnergyReading

# ---------------------------------------------------------------------------
# Normalização de chaves (underscore-insensitive)
# ---------------------------------------------------------------------------

def _norm(key: str) -> str:
    """Remove underscores e converte para minúsculas — para lookup no payload."""
    return key.replace("_", "").lower()


# Mapa: chave normalizada → nome canônico no payload (sem underscore).
# Somente para campos com aliases conhecidos (deltas divergem doc vs payload).
_ALIAS_MAP: dict[str, str] = {
    _norm("deltaeptc"): "deltaeptc",
    _norm("delta_ept_c"): "deltaeptc",
    _norm("deltaeptg"): "deltaeptg",
    _norm("delta_ept_g"): "deltaeptg",
}


def _get(obj_norm: dict[str, str], key: str) -> Optional[str]:
    """
    Busca valor no payload por chave normalizada.
    Resolve aliases de delta antes do lookup.
    Retorna a string bruta ou None se ausente.
    """
    canonical = _ALIAS_MAP.get(_norm(key), _norm(key))
    return obj_norm.get(canonical)


# ---------------------------------------------------------------------------
# Conversores de tipo
# ---------------------------------------------------------------------------

_GSM_NO_SIGNAL = -999


def _sf(v: Optional[str]) -> Optional[float]:
    """String → float; None ou não-conversível → None. Preserva negativos."""
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _si(v: Optional[str]) -> Optional[int]:
    """String → int (via float para suportar '20.0'); None ou inválido → None."""
    if v is None:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _sdecimal(v: Optional[str]) -> Optional[str]:
    """
    Valida que v é um número decimal válido e retorna a string normalizada.
    Acumuladores são guardados como string para não perder precisão NUMERIC(18,3).
    Retorna None se ausente ou não-conversível.
    """
    if v is None:
        return None
    try:
        # Valida parseabilidade; retorna string com ponto decimal
        return str(float(v))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Parser principal
# ---------------------------------------------------------------------------

def _parse_json(obj: dict) -> EnergyParseResult:
    # Normaliza todas as chaves para lookup uniforme (remove underscores, lower)
    obj_norm: dict[str, str] = {_norm(k): str(v) for k, v in obj.items()}

    device_id = obj_norm.get("id") or ""
    if not device_id:
        return EnergyParseResult(status="failed", reason="missing_device_id")

    # Sinal GSM: campo varia por firmware — tenta rssi_gsm, cai para rssi_modem.
    # -999 → None (sem sinal GSM)
    rssi_raw = _si(_get(obj_norm, "rssi_gsm"))
    if rssi_raw is None:
        rssi_raw = _si(_get(obj_norm, "rssi_modem"))
    gsm_rssi = None if rssi_raw == _GSM_NO_SIGNAL else rssi_raw

    reading = EnergyReading(
        device_external_id=device_id,
        # Instantâneos
        active_power_total_w=_sf(_get(obj_norm, "pt")),
        reactive_power_total_var=_sf(_get(obj_norm, "qt")),
        voltage_phase_a_v=_sf(_get(obj_norm, "uarms")),
        voltage_phase_b_v=_sf(_get(obj_norm, "ubrms")),
        voltage_phase_c_v=_sf(_get(obj_norm, "ucrms")),
        current_total_a=_sf(_get(obj_norm, "itrms")),
        power_factor_total=_sf(_get(obj_norm, "pft")),
        # Acumulados — string decimal
        active_energy_consumed_total_kwh=_sdecimal(_get(obj_norm, "ept_c")),
        active_energy_generated_total_kwh=_sdecimal(_get(obj_norm, "ept_g")),
        reactive_energy_generated_total_kvarh=_sdecimal(_get(obj_norm, "eqt_g")),
        # Deltas (aliases deltaeptc/delta_ept_c normalizados)
        delta_active_energy_consumed_kwh=_sdecimal(_get(obj_norm, "deltaeptc")),
        delta_active_energy_generated_kwh=_sdecimal(_get(obj_norm, "deltaeptg")),
        # Diagnóstico
        gsm_signal_rssi_dbm=gsm_rssi,
    )

    return EnergyParseResult(status="ok", reason="ok", reading=reading)


# ---------------------------------------------------------------------------
# Entrypoint público
# ---------------------------------------------------------------------------

def parse(payload_raw: str) -> EnergyParseResult:
    """
    Parseia payload bruto do SM-3EGW (/param_energ).

    Nunca lança — erros retornam EnergyParseResult(status="failed").
    Campos ausentes → None; não-conversíveis → None; rssi_gsm=-999 → None.
    Acumulados retornados como string decimal para precisão NUMERIC(18,3).
    """
    if not payload_raw or not payload_raw.strip():
        return EnergyParseResult(status="failed", reason="empty_payload")

    start = payload_raw.find("{")
    if start < 0:
        return EnergyParseResult(status="failed", reason="no_json_object")

    try:
        obj = json.loads(payload_raw[start:])
        if not isinstance(obj, dict):
            return EnergyParseResult(status="failed", reason="not_a_dict")
        return _parse_json(obj)
    except json.JSONDecodeError:
        return EnergyParseResult(status="failed", reason="invalid_json")
    except Exception:
        return EnergyParseResult(status="failed", reason="unexpected_error")
