"""
Golden tests para sn50_analog.py (DTN-200-FPS0).

Valida:
  - 6 leituras extraídas (cabeçalho + 5 slots históricos)
  - current_ma correto (cabeçalho e histórico)
  - Timestamps UTC direto
  - Fallback de nomes de campo (idc_input / idc_intput)
  - Slots com ts epoch ignorados silenciosamente
  - current_ma fora de faixa → sem level (verificado em analog_level, não aqui)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.processing.parsers import sn50_analog
from app.processing.parsers.base import ParseResult

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "payloads"


def _load(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def _load_expected(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Golden test — payload real com idc_intput (typo firmware)
# ---------------------------------------------------------------------------

class TestGoldenSn50Analog:
    def test_status_ok(self):
        result = sn50_analog.parse(_load("sn50_analog.json"))
        assert result.status == "ok", f"expected ok, got {result.status}: {result.reason}"

    def test_reading_count(self):
        result = sn50_analog.parse(_load("sn50_analog.json"))
        assert len(result.readings) == 6

    def test_header_reading(self):
        result = sn50_analog.parse(_load("sn50_analog.json"))
        header = result.readings[0]
        assert header.hist_index == 0
        assert header.imei == "860751074046688"
        assert abs(header.current_ma - 12.508) < 0.001
        assert header.voltage_v == 0.0
        assert header.signal == 20
        assert abs(header.battery - 3.65) < 0.001
        assert header.collected_at_utc.tzinfo is not None
        assert header.collected_at_utc.isoformat() == "2026-06-17T10:00:00+00:00"

    def test_historical_readings(self):
        result = sn50_analog.parse(_load("sn50_analog.json"))
        for i, reading in enumerate(result.readings[1:], start=1):
            assert reading.hist_index == i
            assert reading.imei == "860751074046688"
            assert reading.current_ma is not None
            assert reading.signal is None   # histórico não tem signal/battery
            assert reading.battery is None

    def test_timestamps_utc(self):
        result = sn50_analog.parse(_load("sn50_analog.json"))
        for r in result.readings:
            assert r.collected_at_utc.tzinfo is not None
            assert r.collected_at_utc.utcoffset().total_seconds() == 0


# ---------------------------------------------------------------------------
# Fallback de campo: idc_input (nome correto, sem typo)
# ---------------------------------------------------------------------------

class TestFieldFallback:
    def test_idc_input_correct_name(self):
        payload = json.dumps({
            "IMEI": "860751074046688",
            "Model": "DTN-200-FPS0",
            "time": "2026/06/17 10:00:00",
            "battery": 3.6,
            "signal": 18,
            "idc_input": 10.0,    # nome correto (sem typo)
            "vdc_input": 1.5,
        })
        result = sn50_analog.parse(payload)
        assert result.status == "ok"
        assert result.readings[0].current_ma == 10.0
        assert result.readings[0].voltage_v == 1.5

    def test_idc_intput_typo_name(self):
        payload = json.dumps({
            "IMEI": "860751074046688",
            "Model": "DTN-200-FPS0",
            "time": "2026/06/17 10:00:00",
            "battery": 3.6,
            "signal": 18,
            "idc_intput": 10.0,   # typo de firmware
            "vdc_intput": 1.5,
        })
        result = sn50_analog.parse(payload)
        assert result.status == "ok"
        assert result.readings[0].current_ma == 10.0
        assert result.readings[0].voltage_v == 1.5


# ---------------------------------------------------------------------------
# Slots com ts epoch são ignorados
# ---------------------------------------------------------------------------

class TestEpochTimestampIgnored:
    def test_epoch_slot_ignored(self):
        payload = json.dumps({
            "IMEI": "860751074046688",
            "Model": "DTN-200-FPS0",
            "time": "2026/06/17 10:00:00",
            "battery": 3.6,
            "signal": 18,
            "idc_intput": 10.0,
            "vdc_intput": 0.0,
            "1": [4.0, 0.0, "1970/01/01 00:00:00"],  # epoch → ignorado
            "2": [5.0, 0.0, "2026/06/17 09:50:00"],   # válido
        })
        result = sn50_analog.parse(payload)
        # header + 1 histórico válido (slot epoch ignorado)
        assert len(result.readings) == 2
        assert result.readings[1].collected_at_utc.year == 2026


# ---------------------------------------------------------------------------
# Falha de sensor — corrente fora de faixa
# ---------------------------------------------------------------------------

class TestSensorFaultCurrentRange:
    def test_undercurrent_still_parseable(self):
        """current_ma < 4 mA → parseia normalmente, fault é detectado pelo derive_worker."""
        payload = json.dumps({
            "IMEI": "860751074046688",
            "Model": "DTN-200-FPS0",
            "time": "2026/06/17 10:00:00",
            "battery": 3.6,
            "signal": 18,
            "idc_intput": 2.0,  # abaixo do mínimo válido
            "vdc_intput": 0.0,
        })
        result = sn50_analog.parse(payload)
        assert result.status == "ok"
        assert result.readings[0].current_ma == 2.0  # visível para diagnóstico

    def test_overrange_still_parseable(self):
        """current_ma > 20.5 mA → parseia normalmente."""
        payload = json.dumps({
            "IMEI": "860751074046688",
            "Model": "DTN-200-FPS0",
            "time": "2026/06/17 10:00:00",
            "battery": 3.6,
            "signal": 18,
            "idc_intput": 21.5,  # acima do máximo
            "vdc_intput": 0.0,
        })
        result = sn50_analog.parse(payload)
        assert result.status == "ok"
        assert result.readings[0].current_ma == 21.5


# ---------------------------------------------------------------------------
# Erros de payload
# ---------------------------------------------------------------------------

class TestErrors:
    def test_empty_payload(self):
        result = sn50_analog.parse("")
        assert result.failed

    def test_missing_imei(self):
        payload = json.dumps({"Model": "DTN-200-FPS0", "time": "2026/06/17 10:00:00"})
        result = sn50_analog.parse(payload)
        assert result.failed

    def test_wrong_model(self):
        payload = json.dumps({
            "IMEI": "860751074046688",
            "Model": "SN50V3-NB",   # Dragino, não analógico
            "time": "2026/06/17 10:00:00",
        })
        result = sn50_analog.parse(payload)
        assert result.failed


# ---------------------------------------------------------------------------
# Dedup: sem duplicidade por (device_id, collected_at_utc)
# ---------------------------------------------------------------------------

class TestDedup:
    def test_no_duplicate_timestamps(self):
        """Cabeçalho e slot '1' nunca devem ter o mesmo timestamp."""
        result = sn50_analog.parse(_load("sn50_analog.json"))
        timestamps = [r.collected_at_utc for r in result.readings]
        assert len(timestamps) == len(set(timestamps)), "Timestamps duplicados detectados"
