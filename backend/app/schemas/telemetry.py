from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class SeriesRow(BaseModel):
    """Uma linha da série temporal — campos variam conforme métricas disponíveis."""
    collected_at_utc: str  # ISO 8601 com Z
    pressure: Optional[float] = None
    pressure2: Optional[float] = None
    level_pct: Optional[float] = None
    level_mca: Optional[float] = None
    level_m: Optional[float] = None
    flow1_lph: Optional[float] = None
    flow2_lph: Optional[float] = None
    flow_total_lph: Optional[float] = None
    flow1_m3h: Optional[float] = None
    flow2_m3h: Optional[float] = None
    flow_total_m3h: Optional[float] = None
    temperature: Optional[float] = None
    battery_v: Optional[float] = None
    # Raw pulse counters (from parsed_measurements). Exposed so the frontend
    # can compute flow using the legacy logic (Δcount / Δt over 1h).
    count_pulses: Optional[float] = None
    count2_pulses: Optional[float] = None


class SeriesResponse(BaseModel):
    installation_slug: str
    rows: list[SeriesRow]
    total: int
    # Início da janela de exibição (UTC ISO-8601 Z). Os pontos antes disso
    # são seed de cálculo e devem ser aparados pelo frontend.
    window_from_utc: Optional[str] = None


class MetricSnapshot(BaseModel):
    value: Optional[float]
    unit: Optional[str]
    derived_at_utc: Optional[str]


class DashboardResponse(BaseModel):
    installation_slug: str
    installation_name: str
    last_seen_utc: Optional[str]
    metrics: dict[str, MetricSnapshot]
    active_alerts: int
