from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, model_validator


class InstallationStatusOut(BaseModel):
    """Estado operacional da instalação relevante para o sistema de alertas."""
    environment: str
    learning_mode_until: Optional[str] = None  # ISO-8601 UTC ou None
    baseline_ready_at: Optional[str] = None    # ISO-8601 UTC ou None
    is_learning: bool = False     # learning_mode_until ainda está no futuro
    has_baseline: bool = False    # baseline_ready_at foi definido


class AlertStateOut(BaseModel):
    installation_slug: str
    rule_key: str
    alert_type: str
    severity: str
    is_active: bool
    current_value: Optional[float]
    first_triggered_at: Optional[str]
    last_triggered_at: Optional[str]
    last_resolved_at: Optional[str]
    # Campos ricos (v2)
    titulo: Optional[str] = None
    mensagem_usuario: Optional[str] = None
    recomendacao: Optional[str] = None
    dados_relevantes: Optional[dict[str, Any]] = None
    # Flag de "visto" para o usuário autenticado
    viewed_by_user: bool = False
    # Legado — mantidos para compatibilidade com o mapper do front
    metric_name: Optional[str] = None
    operator: Optional[str] = None
    threshold: Optional[float] = None
    # Extraídos de dados_relevantes para acesso tipado
    event_time: Optional[str] = None
    z_score: Optional[float] = None
    baseline_mean: Optional[float] = None
    baseline_p90: Optional[float] = None
    sample_size: Optional[int] = None

    @model_validator(mode="after")
    def _extract_dados_relevantes(self) -> "AlertStateOut":
        dr = self.dados_relevantes or {}
        if self.event_time is None:
            self.event_time = dr.get("event_time")
        if self.z_score is None:
            v = dr.get("z_score")
            self.z_score = float(v) if v is not None else None
        if self.baseline_mean is None:
            v = dr.get("baseline_lph")
            self.baseline_mean = float(v) if v is not None else None
        if self.baseline_p90 is None:
            v = dr.get("baseline_p90")
            self.baseline_p90 = float(v) if v is not None else None
        if self.sample_size is None:
            v = dr.get("sample_count")
            self.sample_size = int(v) if v is not None else None
        return self


class AlertEventOut(BaseModel):
    installation_slug: str
    rule_key: str
    alert_type: str
    severity: str
    message: Optional[str]
    status: str  # 'ativo' | 'resolvido'
    current_value: Optional[float]
    triggered_at: str
    # Campos ricos (v2)
    titulo: Optional[str] = None
    mensagem_usuario: Optional[str] = None
    recomendacao: Optional[str] = None
    dados_relevantes: Optional[dict[str, Any]] = None


class AlertsResponse(BaseModel):
    states: list[AlertStateOut]
    recent_events: list[AlertEventOut]
    installation_statuses: dict[str, InstallationStatusOut] = {}
