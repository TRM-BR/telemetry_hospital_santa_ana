"""
app/processing/parsers/dragino_sn50.py — Parser para Dragino SN50V3-NB.

Lógica extraída de comunication/bridge_dragino.py:268-590 (legado).
Refatorada para:
  - Retornar ParseResult / ParsedReading (sem efeitos colaterais)
  - Separar path feliz do fallback de JSON quebrado
  - Tratar chunked delivery (campos "Hist" e "Chunk")
  - Confirmar timezone UTC (validado na Fase 1 / Fase 5)

Formato de payload Dragino SN50V3-NB:
  {
    "IMEI": "868927084623920",
    "IMSI": "...",
    "Model": "SN50V3-NB",
    "mod": 1,
    "battery": 3.55,
    "signal": 24,
    "time": "2026/05/20 18:38:33",   # UTC (confirmado)
    "temperature": 23.5,              # opcional
    "temperature2": 22.1,             # opcional
    "pressure": 1234.5,               # opcional (raw — derivation converte p/ MCA)
    "pressure2": 1200.0,              # opcional
    "count": 4500,                    # opcional (pulsos)
    "count2": 3200,                   # opcional
    "Hist": "16/59",                  # opcional — indica chunk histórico
    "Chunk": "1/4",                   # opcional — número do pacote
    "16": [23.5, 1234.0, 22.0, 1200.0, 4500, 3200, "2026/05/20 15:33:00"],  # mod=1
    "17": [23.6, 1235.0, 22.1, 1201.0, 4501, 3201, "2026/05/20 15:38:00"],
    ...
  }

Modos históricos:
  mod=1: [temp1, pres1, temp2, pres2, count, count2, "YYYY/MM/DD HH:MM:SS"]  (7 campos)
  mod=2: [temp1, pres1, count, count2, "YYYY/MM/DD HH:MM:SS"]                (5 campos)
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Optional

from app.processing.parsers.base import ParseResult, ParsedReading

# Formato de timestamp nos payloads Dragino
_TS_FMT = "%Y/%m/%d %H:%M:%S"


# ---------------------------------------------------------------------------
# Helpers de conversão seguros
# ---------------------------------------------------------------------------

def _sf(x: object) -> Optional[float]:
    """Converte para float; retorna None em falha."""
    try:
        return float(x)  # type: ignore[arg-type]
    except Exception:
        return None


def _si(x: object) -> Optional[int]:
    """Converte para int; retorna None em falha."""
    try:
        return int(float(x))  # type: ignore[arg-type]
    except Exception:
        return None


def _parse_ts(s: object) -> Optional[datetime]:
    """Converte string 'YYYY/MM/DD HH:MM:SS' para datetime UTC consciente."""
    if not isinstance(s, str):
        return None
    try:
        return datetime.strptime(s, _TS_FMT).replace(tzinfo=timezone.utc)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Parser principal (JSON válido)
# ---------------------------------------------------------------------------

def _parse_json(obj: dict) -> ParseResult:
    """
    Parseia um objeto JSON já decodificado.
    Extrai leitura atual + leituras históricas (chaves numéricas).
    """
    imei = str(obj.get("IMEI") or obj.get("imei") or "").strip()
    if not imei:
        return ParseResult(status="failed", reason="missing_imei")

    mode_raw = obj.get("mod")
    try:
        mode = int(mode_raw)  # type: ignore[arg-type]
    except Exception:
        mode = None

    readings: list[ParsedReading] = []
    parse_issues = 0
    expected_hist = 0
    parsed_hist = 0

    # ── Leitura atual (hist_index=0) ────────────────────────────────────────
    ts_main = _parse_ts(obj.get("time"))
    if ts_main:
        readings.append(ParsedReading(
            imei=imei,
            hist_index=0,
            collected_at_utc=ts_main,
            temperature1=_sf(obj.get("temperature")),
            temperature2=_sf(obj.get("temperature2")),
            pressure1=_sf(obj.get("pressure")),
            pressure2=_sf(obj.get("pressure2")),
            count1=_sf(obj.get("count") if obj.get("count") is not None else obj.get("count_pa4")),
            count2=_sf(obj.get("count2") if obj.get("count2") is not None else obj.get("count_pa0")),
            signal=_si(obj.get("signal")),
            battery=_sf(obj.get("battery")),
        ))

    # ── Leituras históricas (chaves numéricas) ───────────────────────────────
    # As chaves numéricas representam o índice histórico no payload.
    # Iteramos em ordem numérica para hist_index sequencial (1, 2, 3...).
    hist_entries: list[tuple[int, list]] = sorted(
        [(int(k), v) for k, v in obj.items() if k.isdigit() and isinstance(v, list)],
        key=lambda x: x[0],
    )

    for seq, (_, v) in enumerate(hist_entries, start=1):
        expected_hist += 1

        # mod=1: [temp1, pres1, temp2, pres2, count, count2, ts]
        if (mode == 1 or mode is None) and len(v) >= 7:
            try:
                ts_h = _parse_ts(v[6])
                if ts_h is None:
                    raise ValueError("bad ts")
                readings.append(ParsedReading(
                    imei=imei,
                    hist_index=seq,
                    collected_at_utc=ts_h,
                    temperature1=_sf(v[0]),
                    pressure1=_sf(v[1]),
                    temperature2=_sf(v[2]),
                    pressure2=_sf(v[3]),
                    count1=_sf(v[4]),
                    count2=_sf(v[5]),
                ))
                parsed_hist += 1
                continue
            except Exception:
                if mode == 1:
                    parse_issues += 1
                    continue

        # mod=2: [temp1, pres1, count, count2, ts]
        if (mode == 2 or mode is None) and len(v) >= 5:
            try:
                ts_h = _parse_ts(v[4])
                if ts_h is None:
                    raise ValueError("bad ts")
                readings.append(ParsedReading(
                    imei=imei,
                    hist_index=seq,
                    collected_at_utc=ts_h,
                    temperature1=_sf(v[0]),
                    pressure1=_sf(v[1]),
                    count1=_sf(v[2]),
                    count2=_sf(v[3]),
                ))
                parsed_hist += 1
                continue
            except Exception:
                pass

        parse_issues += 1

    if not readings:
        return ParseResult(status="failed", reason="no_valid_readings")

    if parse_issues > 0 or (expected_hist > 0 and parsed_hist < expected_hist):
        return ParseResult(
            status="partial",
            reason="partial_histories",
            readings=readings,
        )

    return ParseResult(status="ok", reason="ok", readings=readings)


# ---------------------------------------------------------------------------
# Fallback para JSON quebrado
# ---------------------------------------------------------------------------

_PAT_MOD1 = re.compile(
    r'"(?P<idx>\d+)"\s*:\s*\[\s*'
    r'(?P<t1>-?\d+(?:\.\d+)?)\s*,\s*'
    r'(?P<p1>-?\d+(?:\.\d+)?)\s*,\s*'
    r'(?P<t2>-?\d+(?:\.\d+)?)\s*,\s*'
    r'(?P<p2>-?\d+(?:\.\d+)?)\s*,\s*'
    r'(?P<c1>-?\d+(?:\.\d+)?)\s*,\s*'
    r'(?P<c2>-?\d+(?:\.\d+)?)\s*,\s*'
    r'"(?P<ts>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})"\s*\]'
)
_PAT_MOD2 = re.compile(
    r'"(?P<idx>\d+)"\s*:\s*\[\s*'
    r'(?P<t1>-?\d+(?:\.\d+)?)\s*,\s*'
    r'(?P<p1>-?\d+(?:\.\d+)?)\s*,\s*'
    r'(?P<c1>-?\d+(?:\.\d+)?)\s*,\s*'
    r'(?P<c2>-?\d+(?:\.\d+)?)\s*,\s*'
    r'"(?P<ts>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})"\s*\]'
)
_PAT_STR = re.compile(r'"(\w+)"\s*:\s*"([^"]+)"')
_PAT_NUM = re.compile(r'"(\w+)"\s*:\s*(-?\d+(?:\.\d+)?)')


def _parse_broken(raw: str) -> ParseResult:
    """
    Fallback regex para payloads com JSON malformado.
    Extrai o que for possível; classifica como "partial" se recuperou algo.
    """
    str_fields = {m.group(1): m.group(2) for m in _PAT_STR.finditer(raw)}
    num_fields = {m.group(1): m.group(2) for m in _PAT_NUM.finditer(raw)}

    imei = str_fields.get("IMEI") or str_fields.get("imei") or ""
    if not imei:
        return ParseResult(status="failed", reason="missing_imei_broken_json")

    readings: list[ParsedReading] = []

    # Leitura principal
    ts_main = _parse_ts(str_fields.get("time"))
    if ts_main:
        readings.append(ParsedReading(
            imei=imei,
            hist_index=0,
            collected_at_utc=ts_main,
            temperature1=_sf(num_fields.get("temperature")),
            temperature2=_sf(num_fields.get("temperature2")),
            pressure1=_sf(num_fields.get("pressure")),
            pressure2=_sf(num_fields.get("pressure2")),
            count1=_sf(num_fields.get("count") or num_fields.get("count_pa4")),
            count2=_sf(num_fields.get("count2") or num_fields.get("count_pa0")),
            signal=_si(num_fields.get("signal")),
            battery=_sf(num_fields.get("battery")),
        ))

    # Históricas via regex
    seen: set[tuple[str, str]] = set()
    matches_m1 = [("m1", m) for m in _PAT_MOD1.finditer(raw)]
    matches_m2 = [("m2", m) for m in _PAT_MOD2.finditer(raw)]

    for seq, (kind, m) in enumerate(matches_m1 + matches_m2, start=1):
        key = (m.group("idx"), m.group("ts"))
        if key in seen:
            continue
        seen.add(key)

        ts_h = _parse_ts(m.group("ts"))
        if ts_h is None:
            continue

        if kind == "m1":
            readings.append(ParsedReading(
                imei=imei,
                hist_index=seq,
                collected_at_utc=ts_h,
                temperature1=_sf(m.group("t1")),
                pressure1=_sf(m.group("p1")),
                temperature2=_sf(m.group("t2")),
                pressure2=_sf(m.group("p2")),
                count1=_sf(m.group("c1")),
                count2=_sf(m.group("c2")),
            ))
        else:
            readings.append(ParsedReading(
                imei=imei,
                hist_index=seq,
                collected_at_utc=ts_h,
                temperature1=_sf(m.group("t1")),
                pressure1=_sf(m.group("p1")),
                count1=_sf(m.group("c1")),
                count2=_sf(m.group("c2")),
            ))

    if not readings:
        return ParseResult(status="failed", reason="broken_json_no_valid_readings")

    return ParseResult(status="partial", reason="broken_json_recovered", readings=readings)


# ---------------------------------------------------------------------------
# Entrypoint público
# ---------------------------------------------------------------------------

def parse(payload_raw: str) -> ParseResult:
    """
    Parseia um payload bruto do Dragino SN50V3-NB.

    Tenta JSON válido primeiro; cai no fallback regex se falhar.
    Nunca lança exceção — erros viram ParseResult(status="failed").

    Args:
        payload_raw: string UTF-8 do campo payload_raw em raw_messages.

    Returns:
        ParseResult com lista de ParsedReading (possivelmente vazia).
    """
    if not payload_raw or not payload_raw.strip():
        return ParseResult(status="failed", reason="empty_payload")

    # Tenta extrair o primeiro bloco JSON válido (ignora lixo antes/depois)
    start = payload_raw.find("{")
    if start < 0:
        return ParseResult(status="failed", reason="no_json_object")

    # Tenta parse direto; se falhar usa fallback
    try:
        obj = json.loads(payload_raw[start:])
        if not isinstance(obj, dict):
            raise ValueError("not a dict")
        return _parse_json(obj)
    except Exception:
        pass

    # Fallback: JSON parcialmente quebrado
    return _parse_broken(payload_raw)
