"""
app/processing/parsers/sn50_analog.py — Parser para DTN-200-FPS0 (SN50_analog).

Formato de payload SN50_analog/data:
  {
    "IMEI": "860751074046688",
    "Model": "DTN-200-FPS0",
    "time": "2026/06/01 10:00:00",   # UTC (confirmado) — leitura ATUAL (cabeçalho)
    "battery": 3.6,
    "signal": 20,
    "idc_intput": 12.5,              # corrente mA (typo de firmware; aceita idc_input)
    "vdc_intput": 2.4,               # tensão V   (typo de firmware; aceita vdc_input)
    "1": [8.508, 0.000, "2026/06/01 09:50:00"],   # [corrente_mA, tensão_V, ts]
    "2": [8.510, 0.000, "2026/06/01 09:40:00"],
    "3": [8.512, 0.000, "2026/06/01 09:30:00"],
    "4": [8.515, 0.000, "2026/06/01 09:20:00"],
    "5": [8.520, 0.000, "2026/06/01 09:10:00"]
  }

Regras:
  - Cabeçalho (hist_index=0): campos "time", "idc_intput|idc_input", "vdc_intput|vdc_input",
    "battery", "signal".
  - Histórico "1"–"5" (hist_index=1–5): [corrente_mA, tensão_V, "ts"].
  - Slots com ts epoch (1970/...) são ignorados.
  - Nunca lança — erros retornam ParseResult(status="failed").
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Optional

from app.processing.parsers.base import ParseResult, ParsedReading

_TS_FMT = "%Y/%m/%d %H:%M:%S"
_EPOCH_PREFIX = "1970/"

# Número mínimo de dígitos para IMEI válido
_IMEI_MIN_LEN = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sf(x: object) -> Optional[float]:
    try:
        return float(x)  # type: ignore[arg-type]
    except Exception:
        return None


def _si(x: object) -> Optional[int]:
    try:
        return int(float(x))  # type: ignore[arg-type]
    except Exception:
        return None


def _parse_ts(s: object) -> Optional[datetime]:
    """Converte 'YYYY/MM/DD HH:MM:SS' para datetime UTC; rejeita epoch."""
    if not isinstance(s, str):
        return None
    if s.startswith(_EPOCH_PREFIX):
        return None
    try:
        return datetime.strptime(s, _TS_FMT).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _get_current(obj: dict, field_typo: str, field_correct: str) -> Optional[float]:
    """Tenta o typo de firmware primeiro, depois o nome correto."""
    v = obj.get(field_typo)
    if v is None:
        v = obj.get(field_correct)
    return _sf(v)


# ---------------------------------------------------------------------------
# Parser JSON
# ---------------------------------------------------------------------------

def _parse_json(obj: dict) -> ParseResult:
    imei = str(obj.get("IMEI") or obj.get("imei") or "").strip()
    if not imei or not imei.isdigit() or len(imei) < _IMEI_MIN_LEN:
        return ParseResult(status="failed", reason="missing_or_invalid_imei")

    # Valida que é um payload analógico DTN
    model = str(obj.get("Model") or obj.get("model") or "").strip()
    if model and not model.upper().startswith("DTN"):
        return ParseResult(status="failed", reason=f"unexpected_model:{model}")

    readings: list[ParsedReading] = []
    parse_issues = 0

    # ── Leitura atual (hist_index=0, cabeçalho) ─────────────────────────────
    ts_main = _parse_ts(obj.get("time"))
    if ts_main:
        current_ma = _get_current(obj, "idc_intput", "idc_input")
        voltage_v = _get_current(obj, "vdc_intput", "vdc_input")
        readings.append(ParsedReading(
            imei=imei,
            hist_index=0,
            collected_at_utc=ts_main,
            current_ma=current_ma,
            voltage_v=voltage_v,
            signal=_si(obj.get("signal")),
            battery=_sf(obj.get("battery")),
        ))

    # ── Histórico "1"–"5": [corrente_mA, tensão_V, ts] ──────────────────────
    hist_entries: list[tuple[int, list]] = sorted(
        [(int(k), v) for k, v in obj.items() if k.isdigit() and isinstance(v, list)],
        key=lambda x: x[0],
    )

    for seq, (_, v) in enumerate(hist_entries, start=1):
        if len(v) < 3:
            parse_issues += 1
            continue
        ts_h = _parse_ts(v[2])
        if ts_h is None:
            # ts epoch ou inválido → ignora silenciosamente (comportamento esperado)
            continue
        readings.append(ParsedReading(
            imei=imei,
            hist_index=seq,
            collected_at_utc=ts_h,
            current_ma=_sf(v[0]),
            voltage_v=_sf(v[1]),
        ))

    if not readings:
        return ParseResult(status="failed", reason="no_valid_readings")

    if parse_issues > 0:
        return ParseResult(status="partial", reason="partial_histories", readings=readings)

    return ParseResult(status="ok", reason="ok", readings=readings)


# ---------------------------------------------------------------------------
# Fallback regex para JSON quebrado
# ---------------------------------------------------------------------------

_PAT_HIST = re.compile(
    r'"(?P<idx>\d+)"\s*:\s*\[\s*'
    r'(?P<ma>-?\d+(?:\.\d+)?)\s*,\s*'
    r'(?P<v>-?\d+(?:\.\d+)?)\s*,\s*'
    r'"(?P<ts>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})"\s*\]'
)
_PAT_STR = re.compile(r'"(\w+)"\s*:\s*"([^"]+)"')
_PAT_NUM = re.compile(r'"(\w+)"\s*:\s*(-?\d+(?:\.\d+)?)')


def _parse_broken(raw: str) -> ParseResult:
    str_fields = {m.group(1): m.group(2) for m in _PAT_STR.finditer(raw)}
    num_fields = {m.group(1): m.group(2) for m in _PAT_NUM.finditer(raw)}

    imei = str_fields.get("IMEI") or str_fields.get("imei") or ""
    if not imei or not imei.isdigit() or len(imei) < _IMEI_MIN_LEN:
        return ParseResult(status="failed", reason="missing_imei_broken_json")

    readings: list[ParsedReading] = []

    ts_main = _parse_ts(str_fields.get("time"))
    if ts_main:
        current_ma = _sf(num_fields.get("idc_intput") or num_fields.get("idc_input"))
        voltage_v = _sf(num_fields.get("vdc_intput") or num_fields.get("vdc_input"))
        readings.append(ParsedReading(
            imei=imei,
            hist_index=0,
            collected_at_utc=ts_main,
            current_ma=current_ma,
            voltage_v=voltage_v,
            signal=_si(num_fields.get("signal")),
            battery=_sf(num_fields.get("battery")),
        ))

    for seq, m in enumerate(_PAT_HIST.finditer(raw), start=1):
        ts_h = _parse_ts(m.group("ts"))
        if ts_h is None:
            continue
        readings.append(ParsedReading(
            imei=imei,
            hist_index=seq,
            collected_at_utc=ts_h,
            current_ma=_sf(m.group("ma")),
            voltage_v=_sf(m.group("v")),
        ))

    if not readings:
        return ParseResult(status="failed", reason="broken_json_no_valid_readings")

    return ParseResult(status="partial", reason="broken_json_recovered", readings=readings)


# ---------------------------------------------------------------------------
# Entrypoint público
# ---------------------------------------------------------------------------

def parse(payload_raw: str) -> ParseResult:
    """
    Parseia payload bruto de SN50_analog/data (DTN-200-FPS0).

    Tenta JSON válido; cai em fallback regex se falhar.
    Nunca lança — erros viram ParseResult(status="failed").
    """
    if not payload_raw or not payload_raw.strip():
        return ParseResult(status="failed", reason="empty_payload")

    start = payload_raw.find("{")
    if start < 0:
        return ParseResult(status="failed", reason="no_json_object")

    try:
        obj = json.loads(payload_raw[start:])
        if not isinstance(obj, dict):
            raise ValueError("not a dict")
        return _parse_json(obj)
    except Exception:
        pass

    return _parse_broken(payload_raw)
