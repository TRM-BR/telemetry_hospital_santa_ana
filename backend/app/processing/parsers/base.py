"""
app/processing/parsers/base.py — Tipos base para parsers de payload.

Todo parser recebe uma string de payload bruto e devolve
uma lista de ParsedReading. O parse_worker usa isso para
preencher parsed_measurements.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ParsedReading:
    """
    Uma leitura parseada extraída de um raw_message.

    hist_index:
        0 = leitura atual (campo "time" do payload principal)
        1+ = leitura histórica (sequencial dentro do mesmo payload)

    collected_at_utc:
        Timestamp UTC do momento em que o sensor coletou a leitura.
        Vem do campo "time" do payload Dragino (confirmado UTC na Fase 1).

    Campos de sensor: todos opcionais (None se ausente no payload).
        temperature1/2  : temperatura em °C
        pressure1/2     : pressão raw (adimensional — derivation converte para MCA)
        count1/2        : pulsos do contador (derivation calcula vazão)
        signal          : RSSI do sinal NB-IoT (dBm)
        battery         : tensão da bateria (V)
    """

    # Identificação
    imei: str
    hist_index: int  # 0 = atual, 1+ = histórico

    # Timestamp da coleta (UTC)
    collected_at_utc: datetime

    # Sensores — Dragino SN50V3-NB
    temperature1: Optional[float] = None
    temperature2: Optional[float] = None
    pressure1: Optional[float] = None
    pressure2: Optional[float] = None
    count1: Optional[float] = None
    count2: Optional[float] = None
    signal: Optional[int] = None
    battery: Optional[float] = None

    # Sensores — DTN-200-FPS0 (canal analógico 4–20 mA)
    current_ma: Optional[float] = None   # corrente do transdutor (mA)
    voltage_v: Optional[float] = None    # tensão do canal analógico (V)


@dataclass
class ParseResult:
    """
    Resultado completo de um parser para um único raw_message.

    status:
        "ok"      — todas as leituras extraídas sem perda
        "partial" — algumas leituras extraídas, outras falhas
        "failed"  — nenhuma leitura extraída

    readings: lista de ParsedReading (vazia se failed).
    reason:   string curta para diagnóstico (ex.: "missing_imei", "partial_histories").
    """

    status: str  # "ok" | "partial" | "failed"
    reason: str
    readings: list[ParsedReading] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def failed(self) -> bool:
        return self.status == "failed"


# ---------------------------------------------------------------------------
# Tipos de energia — SM-3EGW (IE Tecnologia)
# ---------------------------------------------------------------------------

@dataclass
class EnergyReading:
    """
    Leitura parseada de um payload SM-3EGW (/param_energ).

    Sem timestamp no payload — collected_at_utc vem de received_at_utc
    (horário de chegada na bridge, gerado no app).

    Todos os campos de medição são opcionais (None = campo ausente no payload).
    Acumulados (ept_c, ept_g, eqt_g) são str para preservar precisão NUMERIC(18,3)
    sem perda de float; o worker converte para Decimal antes de gravar.
    """

    # Identidade — valor do campo "id" no payload (ex.: "iemedidor")
    device_external_id: str

    # Instantâneos / fase
    active_power_total_w: Optional[float] = None          # pt  (pode ser negativo)
    reactive_power_total_var: Optional[float] = None      # qt
    voltage_phase_a_v: Optional[float] = None             # uarms
    voltage_phase_b_v: Optional[float] = None             # ubrms
    voltage_phase_c_v: Optional[float] = None             # ucrms
    current_total_a: Optional[float] = None               # itrms
    power_factor_total: Optional[float] = None            # pft

    # Acumulados monotônicos — string decimal para precisão NUMERIC(18,3)
    active_energy_consumed_total_kwh: Optional[str] = None     # ept_c
    active_energy_generated_total_kwh: Optional[str] = None    # ept_g
    reactive_energy_generated_total_kvarh: Optional[str] = None  # eqt_g

    # Deltas por telemetria (só ept_c e ept_g têm delta no payload)
    delta_active_energy_consumed_kwh: Optional[str] = None     # deltaeptc / delta_ept_c
    delta_active_energy_generated_kwh: Optional[str] = None    # deltaeptg / delta_ept_g

    # Diagnóstico
    gsm_signal_rssi_dbm: Optional[int] = None            # rssi_gsm (-999 → None)


@dataclass
class EnergyParseResult:
    """
    Resultado de parse de um payload SM-3EGW.

    status:
        "ok"     — leitura extraída com todos os campos mapeados presentes.
        "failed" — payload inválido (JSON quebrado, vazio, sem device_id).
    reading: EnergyReading se ok, None se failed.
    reason:  string curta para diagnóstico.
    """

    status: str  # "ok" | "failed"
    reason: str
    reading: Optional[EnergyReading] = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def failed(self) -> bool:
        return self.status == "failed"
