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
