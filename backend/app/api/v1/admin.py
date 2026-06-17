"""
app/api/v1/admin.py — Endpoints de administração (admin-only).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AdminUser
from app.schemas.alert_simulation import (
    SimulatedAlertOut,
    SimulationMetaOut,
    SimulationRequest,
    SimulationResponse,
    SimulationSummaryOut,
)
from app.services.alert_simulation_service import run_simulation

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post(
    "/alerts/simulate",
    response_model=SimulationResponse,
    summary="Simula alertas sobre dados históricos (read-only)",
)
async def simulate_alerts(body: SimulationRequest, _user: AdminUser) -> SimulationResponse:
    """
    Avalia o motor de alertas atual sobre dados históricos no período [from_dt, to_dt].

    - 100% read-only: não escreve em alert_state, alert_events nem baselines.
    - Inclui detectores shadow (ex.: variacao_rapida) se include_shadow=True.
    - Janela máxima: 30 dias. Saída máxima: 2000 alertas.
    """
    try:
        result = await run_simulation(
            from_dt=body.from_dt,
            to_dt=body.to_dt,
            installation_slug=body.installation_slug,
            mode=body.mode,
            limit=body.limit,
            step_minutes=body.step_minutes,
            include_shadow=body.include_shadow,
            dedupe_window_minutes=body.dedupe_window_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc

    installation_slugs = [body.installation_slug] if body.installation_slug else []

    return SimulationResponse(
        meta=SimulationMetaOut(
            from_dt=body.from_dt,
            to_dt=body.to_dt,
            installation_slugs=installation_slugs,
            generated_at=result.generated_at,
            read_only=True,
            read_only_confirmed=result.read_only_confirmed,
            evaluations_run=result.evaluations_run,
            truncated=result.truncated,
        ),
        summary=SimulationSummaryOut(
            alerts_total=result.summary.total,
            by_installation=result.summary.by_installation,
            by_rule_key=result.summary.by_rule,
            by_severity=result.summary.by_severity,
            shadow_total=result.summary.shadow_count,
            active_total=result.summary.active_count,
        ),
        alerts=[
            SimulatedAlertOut(
                timestamp=a.timestamp,
                installation_slug=a.installation_slug,
                installation_name=a.installation_name,
                rule_key=a.rule_key,
                severity=a.severity,
                shadow=a.shadow,
                metric_used=a.metric_used,
                current_value=a.current_value,
                observed_value=a.observed_value,
                normal_high=a.normal_high,
                anomaly_high=a.anomaly_high,
                reason=a.reason,
                severity_reason=a.severity_reason,
                mensagem_usuario=a.mensagem_usuario,
                recomendacao=a.recomendacao,
                dados_relevantes=a.dados_relevantes,
                occurrences=a.occurrences,
            )
            for a in result.alerts
        ],
    )
