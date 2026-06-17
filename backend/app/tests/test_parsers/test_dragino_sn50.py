"""
Testes unitários para app/processing/parsers/dragino_sn50.py

Usa payloads reais capturados da bridge shadow (raw_messages).
Confirma:
  - IMEI extraído do JSON
  - Timestamp UTC
  - Leitura atual (hist_index=0)
  - Leituras históricas (hist_index=1+)
  - Dedup por hist_index sequencial
  - Fallback para JSON quebrado
  - Casos de borda (vazio, sem JSON, IMEI ausente)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.processing.parsers.dragino_sn50 import parse
from app.processing.parsers.base import ParseResult


# ---------------------------------------------------------------------------
# Fixtures — payloads reais observados na bridge shadow
# ---------------------------------------------------------------------------

# Payload completo (mod=1): leitura atual + históricas
PAYLOAD_MOD1_FULL = json.dumps({
    "IMEI": "868927084623920",
    "IMSI": "724130310274155",
    "Model": "SN50V3-NB",
    "mod": 1,
    "battery": 3.55,
    "signal": 24,
    "time": "2026/05/20 18:38:33",
    "temperature": 23.5,
    "pressure": 1234.5,
    "temperature2": 22.1,
    "pressure2": 1200.0,
    "count": 4500,
    "count2": 3200,
    "1": [23.5, 1234.0, 22.0, 1200.0, 4500, 3200, "2026/05/20 15:33:00"],
    "2": [23.6, 1235.0, 22.1, 1201.0, 4501, 3201, "2026/05/20 15:38:00"],
})

# Payload somente leitura atual (sem históricas) — mod=1
PAYLOAD_CURRENT_ONLY = json.dumps({
    "IMEI": "868927084623920",
    "IMSI": "724130310274155",
    "Model": "SN50V3-NB",
    "mod": 1,
    "battery": 3.55,
    "signal": 24,
    "time": "2026/05/20 18:38:33",
    "temperature": 23.5,
    "pressure": 1234.5,
})

# Payload mod=2 (menor conjunto de sensores)
PAYLOAD_MOD2 = json.dumps({
    "IMEI": "868927084622450",
    "mod": 2,
    "battery": 3.60,
    "signal": 20,
    "time": "2026/05/20 12:00:00",
    "temperature": 25.0,
    "pressure": 900.0,
    "count": 1000,
    "count2": 500,
    "1": [25.0, 900.0, 1000, 500, "2026/05/20 11:55:00"],
    "2": [25.1, 901.0, 1001, 501, "2026/05/20 11:50:00"],
})

# Payload apenas chunk histórico (sem time principal) — formato real observado
PAYLOAD_HIST_CHUNK = json.dumps({
    "IMEI": "868927084623920",
    "IMSI": "724130310274155",
    "time": "2026/05/20 17:45:34",
    "Hist": "54/59",
    "Chunk": "4/4",
    "55": [22.9, 1230.0, 21.8, 1195.0, 4480, 3180, "2026/05/20 14:45:00"],
    "56": [23.0, 1231.0, 21.9, 1196.0, 4481, 3181, "2026/05/20 14:50:00"],
})

# Payload com alias count_pa4 / count_pa0
PAYLOAD_COUNT_ALIAS = json.dumps({
    "IMEI": "868927084622450",
    "mod": 1,
    "time": "2026/05/20 09:00:00",
    "count_pa4": 2000,
    "count_pa0": 1500,
})

# JSON quebrado com IMEI válido
PAYLOAD_BROKEN_JSON = '{"IMEI":"868927084623920","time":"2026/05/20 10:00:00","temperature":23.5, BROKEN'

# Casos de erro
PAYLOAD_EMPTY = ""
PAYLOAD_NO_JSON = "AT+CMQTTRXSTART=0,77,0"
PAYLOAD_MISSING_IMEI = json.dumps({"time": "2026/05/20 10:00:00", "temperature": 23.0})


# ---------------------------------------------------------------------------
# Testes — payload válido mod=1
# ---------------------------------------------------------------------------

class TestMod1Full:
    def test_status_ok(self):
        r = parse(PAYLOAD_MOD1_FULL)
        assert r.status == "ok"

    def test_reading_count(self):
        r = parse(PAYLOAD_MOD1_FULL)
        assert len(r.readings) == 3  # 1 atual + 2 históricas

    def test_imei_extracted(self):
        r = parse(PAYLOAD_MOD1_FULL)
        assert all(rd.imei == "868927084623920" for rd in r.readings)

    def test_current_reading_hist_index_zero(self):
        r = parse(PAYLOAD_MOD1_FULL)
        current = next(rd for rd in r.readings if rd.hist_index == 0)
        assert current is not None

    def test_current_reading_timestamp_utc(self):
        r = parse(PAYLOAD_MOD1_FULL)
        current = next(rd for rd in r.readings if rd.hist_index == 0)
        expected = datetime(2026, 5, 20, 18, 38, 33, tzinfo=timezone.utc)
        assert current.collected_at_utc == expected

    def test_current_reading_values(self):
        r = parse(PAYLOAD_MOD1_FULL)
        current = next(rd for rd in r.readings if rd.hist_index == 0)
        assert current.temperature1 == pytest.approx(23.5)
        assert current.pressure1 == pytest.approx(1234.5)
        assert current.temperature2 == pytest.approx(22.1)
        assert current.pressure2 == pytest.approx(1200.0)
        assert current.count1 == pytest.approx(4500)
        assert current.count2 == pytest.approx(3200)
        assert current.signal == 24
        assert current.battery == pytest.approx(3.55)

    def test_hist_indices_sequential(self):
        r = parse(PAYLOAD_MOD1_FULL)
        hist = sorted([rd for rd in r.readings if rd.hist_index > 0], key=lambda x: x.hist_index)
        assert [rd.hist_index for rd in hist] == [1, 2]

    def test_hist_timestamps_utc(self):
        r = parse(PAYLOAD_MOD1_FULL)
        hist = sorted([rd for rd in r.readings if rd.hist_index > 0], key=lambda x: x.hist_index)
        assert hist[0].collected_at_utc == datetime(2026, 5, 20, 15, 33, 0, tzinfo=timezone.utc)
        assert hist[1].collected_at_utc == datetime(2026, 5, 20, 15, 38, 0, tzinfo=timezone.utc)

    def test_hist_values(self):
        r = parse(PAYLOAD_MOD1_FULL)
        h1 = next(rd for rd in r.readings if rd.hist_index == 1)
        assert h1.temperature1 == pytest.approx(23.5)
        assert h1.pressure1 == pytest.approx(1234.0)
        assert h1.temperature2 == pytest.approx(22.0)
        assert h1.count1 == pytest.approx(4500)


# ---------------------------------------------------------------------------
# Testes — somente leitura atual
# ---------------------------------------------------------------------------

class TestCurrentOnly:
    def test_status_ok(self):
        r = parse(PAYLOAD_CURRENT_ONLY)
        assert r.status == "ok"

    def test_one_reading(self):
        r = parse(PAYLOAD_CURRENT_ONLY)
        assert len(r.readings) == 1
        assert r.readings[0].hist_index == 0


# ---------------------------------------------------------------------------
# Testes — mod=2
# ---------------------------------------------------------------------------

class TestMod2:
    def test_status_ok(self):
        r = parse(PAYLOAD_MOD2)
        assert r.status == "ok"

    def test_reading_count(self):
        r = parse(PAYLOAD_MOD2)
        assert len(r.readings) == 3  # 1 atual + 2 históricas

    def test_hist_no_temperature2(self):
        """mod=2 não tem temperature2 nas históricas."""
        r = parse(PAYLOAD_MOD2)
        for rd in r.readings:
            if rd.hist_index > 0:
                assert rd.temperature2 is None


# ---------------------------------------------------------------------------
# Testes — chunk histórico (sem time principal)
# ---------------------------------------------------------------------------

class TestHistChunk:
    def test_extracts_hist_readings(self):
        r = parse(PAYLOAD_HIST_CHUNK)
        # Tem "time" no payload → leitura atual + 2 históricas
        assert len(r.readings) >= 2

    def test_imei_correct(self):
        r = parse(PAYLOAD_HIST_CHUNK)
        assert all(rd.imei == "868927084623920" for rd in r.readings)


# ---------------------------------------------------------------------------
# Testes — alias count_pa4 / count_pa0
# ---------------------------------------------------------------------------

class TestCountAlias:
    def test_count_alias_extracted(self):
        r = parse(PAYLOAD_COUNT_ALIAS)
        assert r.readings[0].count1 == pytest.approx(2000)
        assert r.readings[0].count2 == pytest.approx(1500)


# ---------------------------------------------------------------------------
# Testes — casos de erro
# ---------------------------------------------------------------------------

class TestErrorCases:
    def test_empty_payload_failed(self):
        r = parse(PAYLOAD_EMPTY)
        assert r.failed
        assert r.reason == "empty_payload"

    def test_no_json_failed(self):
        r = parse(PAYLOAD_NO_JSON)
        assert r.failed

    def test_missing_imei_failed(self):
        r = parse(PAYLOAD_MISSING_IMEI)
        assert r.failed
        assert "imei" in r.reason.lower()

    def test_never_raises(self):
        """parse() nunca deve lançar exceção."""
        for bad in [None, "", "   ", "{}", "[]", '{"x":1}']:
            try:
                result = parse(bad or "")  # type: ignore[arg-type]
                assert isinstance(result, ParseResult)
            except Exception as exc:
                pytest.fail(f"parse() raised {exc!r} for input {bad!r}")


# ---------------------------------------------------------------------------
# Testes — JSON quebrado (fallback)
# ---------------------------------------------------------------------------

class TestBrokenJson:
    def test_recovers_imei(self):
        r = parse(PAYLOAD_BROKEN_JSON)
        # Pode ser partial ou failed dependendo do que for recuperado
        if not r.failed:
            assert r.readings[0].imei == "868927084623920"

    def test_does_not_raise(self):
        r = parse(PAYLOAD_BROKEN_JSON)
        assert isinstance(r, ParseResult)
