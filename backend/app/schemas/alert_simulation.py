"""
app/schemas/alert_simulation.py — Request/Response schemas para a API de simulação de alertas.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

_MAX_DAYS = 30
_MAX_LIMIT = 2000
_MIN_STEP = 1
_MAX_STEP = 1440  # 24h


class SimulationRequest(BaseModel):
    from_dt: datetime = Field(..., description="Início da janela (UTC ISO 8601)")
    to_dt: datetime = Field(..., description="Fim da janela (UTC ISO 8601)")
    installation_slug: str | None = Field(None, description="Slug da instalação; None = todas ativas")
    mode: Literal["real_records", "fixed_step"] = Field("real_records")
    limit: int = Field(500, ge=1, le=_MAX_LIMIT, description="Máximo de alertas na saída")
    step_minutes: int = Field(30, ge=_MIN_STEP, le=_MAX_STEP, description="Passo em minutos (modo fixed_step)")
    include_shadow: bool = Field(True, description="Incluir detectores em shadow-only (ex.: variacao_rapida)")
    dedupe_window_minutes: int = Field(60, ge=0, le=1440)

    @model_validator(mode="after")
    def validate_window(self) -> SimulationRequest:
        if self.from_dt >= self.to_dt:
            raise ValueError("from_dt deve ser anterior a to_dt")
        delta = (self.to_dt - self.from_dt).total_seconds() / 86400
        if delta > _MAX_DAYS:
            raise ValueError(f"Janela máxima é {_MAX_DAYS} dias (solicitado {delta:.1f} dias)")
        return self


class SimulationMetaOut(BaseModel):
    from_dt: datetime
    to_dt: datetime
    installation_slugs: list[str]
    generated_at: datetime
    read_only: bool
    read_only_confirmed: str
    evaluations_run: int
    truncated: bool


class SimulatedAlertOut(BaseModel):
    timestamp: datetime
    installation_slug: str
    installation_name: str
    rule_key: str
    severity: str | None
    shadow: bool
    metric_used: str | None
    current_value: float | None
    observed_value: float | None
    normal_high: float | None
    anomaly_high: float | None
    reason: str | None
    severity_reason: str | None
    mensagem_usuario: str | None
    recomendacao: str | None
    dados_relevantes: dict[str, Any]
    occurrences: int = 1


class SimulationSummaryOut(BaseModel):
    alerts_total: int
    by_installation: dict[str, int]
    by_rule_key: dict[str, int]
    by_severity: dict[str, int]
    shadow_total: int
    active_total: int


class SimulationResponse(BaseModel):
    meta: SimulationMetaOut
    summary: SimulationSummaryOut
    alerts: list[SimulatedAlertOut]
