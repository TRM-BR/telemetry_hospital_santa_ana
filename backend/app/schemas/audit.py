"""
app/schemas/audit.py — Schemas Pydantic para o endpoint de auditoria de alertas.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class AuditCapabilities(BaseModel):
    """Capacidades hidráulicas detectadas da instalação (subset para exibição)."""
    confidence: str                  # "high" | "medium" | "low"
    sample_count: int
    has_street_pressure: bool
    has_tank_pressure: bool
    has_temperature2: bool
    has_street_inlet_counter: bool
    has_tank_outlet_counter: bool
    can_alert_street_pressure: bool
    can_alert_tank: bool
    can_alert_tank_sensor: bool
    can_alert_level: bool
    can_alert_flow_inlet: bool
    can_alert_flow_outlet: bool


class AuditAlert(BaseModel):
    """Detalhe de um evento de alerta com interpretação."""
    event_id: int
    rule_key: str
    titulo: Optional[str] = None
    severity: str
    status: str                         # 'ativo' | 'resolvido'
    is_active: bool                     # estado atual em alert_state
    # Timestamps
    triggered_at: str                   # quando o worker disparou (alert_events)
    resolved_at: Optional[str] = None   # alert_events.resolved_at
    first_triggered_at: Optional[str] = None  # alert_state.first_triggered_at
    last_triggered_at: Optional[str] = None   # alert_state.last_triggered_at
    # Evidência
    evidence_time: Optional[str] = None     # dados_relevantes.evidence_time
    window_start_at: Optional[str] = None
    window_end_at: Optional[str] = None
    # Canal
    metric_used: Optional[str] = None
    channel_role: Optional[str] = None
    channel_role_label: str              # rótulo humano do canal
    # Valores
    observed_value: Optional[float] = None
    observed_unit: Optional[str] = None
    baseline_metric: Optional[str] = None   # "p99" | "p90" | "mean" | etc.
    baseline_value: Optional[float] = None
    threshold_value: Optional[float] = None
    absolute_floor: Optional[float] = None
    sample_count_ref: Optional[int] = None
    points_above_threshold: Optional[int] = None
    window_points: Optional[int] = None
    points_confirming: Optional[int] = None  # para alertas de caixa
    # Campos comportamentais (Fase 9 — extraídos de dados_relevantes)
    normal_high: Optional[float] = None         # limite superior do normal desta instalação
    anomaly_high: Optional[float] = None        # limite de anomalia desta instalação
    baseline_confidence: Optional[str] = None   # "low"|"medium"|"high"|"consolidated"
    period_type: Optional[str] = None           # "overall"|"night"|"day"|"business_hours"|...
    profile_type: Optional[str] = None          # "continuous"|"intermittent"|"variable"|"inactive"
    # Severidade comportamental (Fase 12 — extraídos de dados_relevantes)
    excess_over_normal: Optional[float] = None
    excess_over_normal_pct: Optional[float] = None
    excess_over_anomaly: Optional[float] = None
    excess_over_anomaly_pct: Optional[float] = None
    severity_reason: Optional[str] = None
    composite_evidence: bool = False
    strong_composite_evidence: bool = False
    composite_evidence_factors: list[str] = []
    duration_minutes: Optional[float] = None
    # Interpretação
    reason: Optional[str] = None
    interpretation: str
    data_sufficient: bool
    from_legacy_engine: bool = False  # True = gerado antes do motor de capacidades
    # Dados brutos (para painel técnico)
    dados_relevantes: Optional[dict[str, Any]] = None
    current_value: Optional[float] = None
    mensagem_usuario: Optional[str] = None
    recomendacao: Optional[str] = None


class AuditInstallation(BaseModel):
    installation_id: int
    slug: str
    name: str
    capabilities: AuditCapabilities
    alerts: list[AuditAlert]
    total_active: int
    total_resolved: int


class AuditSummary(BaseModel):
    total_alerts: int
    active_alerts: int
    resolved_alerts: int
    critical_alerts: int
    installations_with_alerts: int


class AuditResponse(BaseModel):
    generated_at: str
    from_dt: Optional[str] = None
    to_dt: Optional[str] = None
    summary: AuditSummary
    installations: list[AuditInstallation]
