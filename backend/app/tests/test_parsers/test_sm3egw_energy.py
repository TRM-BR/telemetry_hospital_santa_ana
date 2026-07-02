"""
Golden tests para sm3egw_energy.py (SM-3EGW, IE Tecnologia).

Valida:
  - Payload real: 11 campos + 2 deltas extraídos corretamente
  - Normalização de nomes de delta (deltaeptc ≡ delta_ept_c)
  - Campo ausente → None (nunca 0)
  - rssi_gsm=-999 → None
  - Negativos preservados (pt negativo)
  - Campos não-mapeados ignorados silenciosamente (~50 extras no fixture)
  - Payload inválido → failed
  - JSON vazio / não-string → failed
  - Valor não-conversível → None (não quebra o lote)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.processing.parsers import sm3egw_energy
from app.processing.parsers.base import EnergyParseResult, EnergyReading

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "payloads"


def _load(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Golden test — payload real completo
# ---------------------------------------------------------------------------

class TestGoldenSm3egwEnergy:
    def setup_method(self):
        self.result = sm3egw_energy.parse(_load("sm3egw_energy.json"))

    def test_status_ok(self):
        assert self.result.status == "ok", f"expected ok: {self.result.reason}"

    def test_reading_not_none(self):
        assert self.result.reading is not None

    def test_device_id(self):
        assert self.result.reading.device_external_id == "iemedidor"

    # Instantâneos
    def test_active_power_negative(self):
        assert abs(self.result.reading.active_power_total_w - (-1250.5)) < 0.001

    def test_reactive_power(self):
        assert abs(self.result.reading.reactive_power_total_var - 340.2) < 0.001

    def test_voltage_a(self):
        assert abs(self.result.reading.voltage_phase_a_v - 220.1) < 0.001

    def test_voltage_b(self):
        assert abs(self.result.reading.voltage_phase_b_v - 219.8) < 0.001

    def test_voltage_c(self):
        assert abs(self.result.reading.voltage_phase_c_v - 221.3) < 0.001

    def test_current_total(self):
        assert abs(self.result.reading.current_total_a - 5.83) < 0.001

    def test_power_factor(self):
        assert abs(self.result.reading.power_factor_total - 0.987) < 0.001

    # Acumulados (string decimal)
    def test_ept_c_string(self):
        r = self.result.reading
        assert r.active_energy_consumed_total_kwh is not None
        assert float(r.active_energy_consumed_total_kwh) == pytest.approx(1234.567, rel=1e-4)

    def test_ept_g_string(self):
        r = self.result.reading
        assert r.active_energy_generated_total_kwh is not None
        assert float(r.active_energy_generated_total_kwh) == pytest.approx(89.012, rel=1e-4)

    def test_eqt_g_string(self):
        r = self.result.reading
        assert r.reactive_energy_generated_total_kvarh is not None
        assert float(r.reactive_energy_generated_total_kvarh) == pytest.approx(45.678, rel=1e-4)

    # Deltas
    def test_delta_ept_c(self):
        r = self.result.reading
        assert r.delta_active_energy_consumed_kwh is not None
        assert float(r.delta_active_energy_consumed_kwh) == pytest.approx(0.123, rel=1e-4)

    def test_delta_ept_g(self):
        r = self.result.reading
        assert r.delta_active_energy_generated_kwh is not None
        assert float(r.delta_active_energy_generated_kwh) == pytest.approx(0.045, rel=1e-4)

    # Diagnóstico
    def test_gsm_rssi(self):
        assert self.result.reading.gsm_signal_rssi_dbm == -75

    # Campos extras ignorados (sem atributos inesperados no reading)
    def test_no_extra_fields_on_reading(self):
        r = self.result.reading
        assert not hasattr(r, "freq")
        assert not hasattr(r, "rssi_wifi")
        assert not hasattr(r, "pa")


# ---------------------------------------------------------------------------
# Normalização de nomes de delta (underscore-insensitive)
# ---------------------------------------------------------------------------

class TestDeltaAliases:
    def test_delta_ept_c_underscore_alias(self):
        payload = json.dumps({"id": "iemedidor", "delta_ept_c": "0.200", "delta_ept_g": "0.100"})
        result = sm3egw_energy.parse(payload)
        assert result.ok
        assert float(result.reading.delta_active_energy_consumed_kwh) == pytest.approx(0.200)

    def test_delta_ept_g_underscore_alias(self):
        payload = json.dumps({"id": "iemedidor", "delta_ept_c": "0.200", "delta_ept_g": "0.100"})
        result = sm3egw_energy.parse(payload)
        assert result.ok
        assert float(result.reading.delta_active_energy_generated_kwh) == pytest.approx(0.100)

    def test_canonical_name_no_underscore(self):
        payload = json.dumps({"id": "iemedidor", "deltaeptc": "0.300", "deltaeptg": "0.150"})
        result = sm3egw_energy.parse(payload)
        assert result.ok
        assert float(result.reading.delta_active_energy_consumed_kwh) == pytest.approx(0.300)
        assert float(result.reading.delta_active_energy_generated_kwh) == pytest.approx(0.150)


# ---------------------------------------------------------------------------
# Campo ausente → None (nunca 0)
# ---------------------------------------------------------------------------

class TestMissingFieldsAreNone:
    def test_missing_instantaneous_fields(self):
        payload = json.dumps({"id": "iemedidor"})
        result = sm3egw_energy.parse(payload)
        assert result.ok
        r = result.reading
        assert r.active_power_total_w is None
        assert r.reactive_power_total_var is None
        assert r.voltage_phase_a_v is None
        assert r.voltage_phase_b_v is None
        assert r.voltage_phase_c_v is None
        assert r.current_total_a is None
        assert r.power_factor_total is None

    def test_missing_accumulators(self):
        payload = json.dumps({"id": "iemedidor"})
        result = sm3egw_energy.parse(payload)
        assert result.ok
        r = result.reading
        assert r.active_energy_consumed_total_kwh is None
        assert r.active_energy_generated_total_kwh is None
        assert r.reactive_energy_generated_total_kvarh is None

    def test_missing_deltas(self):
        payload = json.dumps({"id": "iemedidor"})
        result = sm3egw_energy.parse(payload)
        assert result.ok
        r = result.reading
        assert r.delta_active_energy_consumed_kwh is None
        assert r.delta_active_energy_generated_kwh is None

    def test_missing_gsm(self):
        payload = json.dumps({"id": "iemedidor"})
        result = sm3egw_energy.parse(payload)
        assert result.ok
        assert result.reading.gsm_signal_rssi_dbm is None


# ---------------------------------------------------------------------------
# rssi_gsm = -999 → None (sem GSM)
# ---------------------------------------------------------------------------

class TestGsmNoSignal:
    def test_rssi_minus_999_becomes_none(self):
        payload = json.dumps({"id": "iemedidor", "rssi_gsm": "-999"})
        result = sm3egw_energy.parse(payload)
        assert result.ok
        assert result.reading.gsm_signal_rssi_dbm is None

    def test_rssi_valid_negative_preserved(self):
        payload = json.dumps({"id": "iemedidor", "rssi_gsm": "-80"})
        result = sm3egw_energy.parse(payload)
        assert result.ok
        assert result.reading.gsm_signal_rssi_dbm == -80

    def test_rssi_zero(self):
        payload = json.dumps({"id": "iemedidor", "rssi_gsm": "0"})
        result = sm3egw_energy.parse(payload)
        assert result.ok
        assert result.reading.gsm_signal_rssi_dbm == 0


# ---------------------------------------------------------------------------
# rssi_modem — fallback quando rssi_gsm ausente (firmware real do MED1)
# ---------------------------------------------------------------------------

class TestGsmFallbackRssiModem:
    def test_rssi_modem_used_when_rssi_gsm_absent(self):
        payload = json.dumps({"id": "MED1", "rssi_modem": "-66"})
        result = sm3egw_energy.parse(payload)
        assert result.ok
        assert result.reading.gsm_signal_rssi_dbm == -66

    def test_rssi_modem_minus_999_becomes_none(self):
        payload = json.dumps({"id": "MED1", "rssi_modem": "-999"})
        result = sm3egw_energy.parse(payload)
        assert result.ok
        assert result.reading.gsm_signal_rssi_dbm is None

    def test_rssi_gsm_takes_precedence_over_rssi_modem(self):
        payload = json.dumps({"id": "MED1", "rssi_gsm": "-70", "rssi_modem": "-90"})
        result = sm3egw_energy.parse(payload)
        assert result.ok
        assert result.reading.gsm_signal_rssi_dbm == -70


# ---------------------------------------------------------------------------
# Negativos preservados
# ---------------------------------------------------------------------------

class TestNegativesPreserved:
    def test_negative_active_power(self):
        payload = json.dumps({"id": "iemedidor", "pt": "-500.0"})
        result = sm3egw_energy.parse(payload)
        assert result.ok
        assert result.reading.active_power_total_w == pytest.approx(-500.0)

    def test_negative_accumulator_preserved_as_string(self):
        # Acumulados negativos são improváveis mas não devem explodir
        payload = json.dumps({"id": "iemedidor", "ept_c": "-1.0"})
        result = sm3egw_energy.parse(payload)
        assert result.ok
        assert float(result.reading.active_energy_consumed_total_kwh) == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# Valor não-conversível → None (não quebra o lote)
# ---------------------------------------------------------------------------

class TestNonConvertibleValues:
    def test_string_text_in_float_field(self):
        payload = json.dumps({"id": "iemedidor", "pt": "n/a"})
        result = sm3egw_energy.parse(payload)
        assert result.ok
        assert result.reading.active_power_total_w is None

    def test_null_in_float_field(self):
        payload = json.dumps({"id": "iemedidor", "pt": None})
        result = sm3egw_energy.parse(payload)
        assert result.ok
        assert result.reading.active_power_total_w is None

    def test_invalid_accumulator(self):
        payload = json.dumps({"id": "iemedidor", "ept_c": "ERR"})
        result = sm3egw_energy.parse(payload)
        assert result.ok
        assert result.reading.active_energy_consumed_total_kwh is None


# ---------------------------------------------------------------------------
# Payload inválido → failed
# ---------------------------------------------------------------------------

class TestInvalidPayloads:
    def test_empty_string(self):
        result = sm3egw_energy.parse("")
        assert result.failed
        assert result.reason == "empty_payload"

    def test_whitespace_only(self):
        result = sm3egw_energy.parse("   ")
        assert result.failed

    def test_no_json_object(self):
        result = sm3egw_energy.parse("not json at all")
        assert result.failed

    def test_broken_json(self):
        result = sm3egw_energy.parse("{id: iemedidor")
        assert result.failed

    def test_array_instead_of_object(self):
        result = sm3egw_energy.parse("[1, 2, 3]")
        assert result.failed

    def test_missing_device_id(self):
        payload = json.dumps({"pt": "100.0", "qt": "50.0"})
        result = sm3egw_energy.parse(payload)
        assert result.failed
        assert result.reason == "missing_device_id"

    def test_empty_device_id(self):
        payload = json.dumps({"id": "", "pt": "100.0"})
        result = sm3egw_energy.parse(payload)
        assert result.failed
        assert result.reason == "missing_device_id"
