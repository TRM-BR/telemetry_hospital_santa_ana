"""
/api/v1/alerts — Estados e eventos de alerta (motor v2).

Endpoints:
  GET  /alerts               — lista estados (+ eventos recentes)
  GET  /alerts/audit         — relatório de auditoria dos eventos (read-only)
  POST /alerts/{slug}/{key}/viewed — marca alerta como visto pelo usuário
  DELETE /alerts/{slug}/{key}/viewed — desmarca
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from app.alerts.capabilities import (
    InstallationCapabilities,
    get_installation_capabilities,
)
from app.api.deps import CurrentUser, DbDep
from app.schemas.alerts import (AlertEventOut, AlertStateOut, AlertsResponse,
                                 InstallationStatusOut)
from app.schemas.audit import (AuditAlert, AuditCapabilities, AuditInstallation,
                                AuditResponse, AuditSummary)

router = APIRouter(prefix="/alerts", tags=["alerts"])

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_SQL_STATES = """
    SELECT
        i.slug                  AS installation_slug,
        als.rule_key,
        COALESCE(als.alert_type, 'sensor')  AS alert_type,
        COALESCE(als.severity,  'atencao')  AS severity,
        als.is_active,
        als.current_value,
        COALESCE(als.first_triggered_at, als.last_triggered_at, als.updated_at)
                                AS first_triggered_at,
        als.last_triggered_at,
        als.last_resolved_at,
        als.titulo,
        als.mensagem_usuario,
        als.recomendacao,
        als.dados_relevantes,
        CASE WHEN av.id IS NOT NULL THEN true ELSE false END AS viewed_by_user,
        'production'            AS inst_environment,
        NULL                    AS inst_learning_mode_until,
        NULL                    AS inst_baseline_ready_at
    FROM alert_state als
    JOIN installations i ON i.id = als.installation_id
    LEFT JOIN alert_views av
        ON av.installation_id = als.installation_id
       AND av.rule_key        = als.rule_key
       AND av.user_id         = :user_id
    {states_where}
    ORDER BY als.last_triggered_at DESC NULLS LAST
"""

_SQL_EVENTS = """
    SELECT
        i.slug              AS installation_slug,
        ae.rule_key,
        ae.alert_type,
        ae.severity,
        ae.message,
        ae.status,
        ae.current_value,
        ae.triggered_at,
        ae.titulo,
        ae.mensagem_usuario,
        ae.recomendacao,
        ae.dados_relevantes
    FROM alert_events ae
    JOIN installations i ON i.id = ae.installation_id
    {events_where}
    ORDER BY ae.triggered_at DESC
    LIMIT 50
"""

_SQL_GET_INST_ID = text("""
    SELECT id FROM installations WHERE slug = :slug LIMIT 1
""")

_SQL_UPSERT_VIEW = text("""
    INSERT INTO alert_views (installation_id, rule_key, user_id, viewed_at)
    VALUES (:installation_id, :rule_key, :user_id, now())
    ON CONFLICT (user_id, installation_id, rule_key) DO UPDATE
        SET viewed_at = now()
""")

_SQL_DELETE_VIEW = text("""
    DELETE FROM alert_views
    WHERE installation_id = :installation_id
      AND rule_key = :rule_key
      AND user_id = :user_id
""")

_SQL_VIEWED_KEYS = """
    SELECT av.rule_key
    FROM alert_views av
    JOIN installations i ON i.id = av.installation_id
    WHERE av.user_id = :user_id
      {inst_filter}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts_z(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _current_user_id(user: CurrentUser) -> int:
    raw_id: Any = None

    if isinstance(user, dict):
        raw_id = user.get("id") or user.get("sub")
    else:
        raw_id = getattr(user, "id", None) or getattr(user, "sub", None)

    try:
        return int(raw_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Usuário autenticado inválido")


# ---------------------------------------------------------------------------
# Helpers de auditoria
# ---------------------------------------------------------------------------

_SEVERITY_REASON_LABELS: dict[str, str] = {
    "within_normal_profile":         "dentro do padrão normal da instalação",
    "band":                          "acima do normal, abaixo do limite de anomalia",
    "band_sustained":                "acima do normal de forma sustentada",
    "band_light_composite":          "acima do normal com queda leve da caixa",
    "band_strong_composite":         "acima do normal com queda forte/persistente da caixa",
    "above_anomaly":                 "ultrapassou o limite de anomalia da instalação",
    "above_anomaly_light_composite": "ultrapassou a anomalia com queda leve da caixa",
    "at_least_2x_anomaly":           "atingiu 2× ou mais o limite de anomalia",
    "strong_composite_evidence":     "anomalia com queda forte/persistente da caixa",
}


def _severity_detail_block(dr: dict[str, Any]) -> str:
    """Bloco textual de tópicos de severidade para alertas comportamentais."""
    parts: list[str] = []
    unit = dr.get("observed_unit", "L/h")

    eon = dr.get("excess_over_normal")
    eon_pct = dr.get("excess_over_normal_pct")
    if eon is not None:
        pct_str = f" (+{int(eon_pct)}%)" if eon_pct is not None and float(eon_pct) > 0 else ""
        if float(eon) > 0:
            parts.append(f"• Excesso sobre o normal: +{float(eon):.1f} {unit}{pct_str}.")

    eoa = dr.get("excess_over_anomaly")
    eoa_pct = dr.get("excess_over_anomaly_pct")
    if eoa is not None and float(eoa) > 0:
        pct_str = f" (+{int(eoa_pct)}%)" if eoa_pct is not None and float(eoa_pct) > 0 else ""
        parts.append(f"• Excesso sobre o limite de anomalia: +{float(eoa):.1f} {unit}{pct_str}.")

    severity_reason = dr.get("severity_reason")
    if severity_reason:
        base = severity_reason.split("|")[0]
        label = _SEVERITY_REASON_LABELS.get(base, base)
        parts.append(f"• Classificação: {label}.")
        if "|capped_low" in severity_reason:
            parts.append("• Severidade limitada: baseline com baixa confiança (histórico insuficiente).")
        elif "|capped_medium" in severity_reason:
            parts.append("• Severidade limitada: baseline com confiança média (histórico parcial).")

    strong = dr.get("strong_composite_evidence", False)
    composite = dr.get("composite_evidence", False)
    factors: list[str] = list(dr.get("composite_evidence_factors") or [])
    if strong:
        parts.append("• Evidência composta forte: queda de caixa confirmada junto com fluxo anômalo.")
    elif composite:
        parts.append("• Evidência composta leve: queda de caixa detectada junto com fluxo elevado.")
    if factors:
        parts.append(f"• Fatores detectados: {', '.join(factors)}.")

    dm = dr.get("duration_minutes")
    if dm is not None:
        dmf = float(dm)
        dur_str = f"{dmf / 60:.0f}h" if dmf >= 60 else f"{int(dmf)} min"
        parts.append(f"• Janela de análise: {dur_str}.")

    return ("\n" + "\n".join(parts)) if parts else ""


def _channel_role_label(channel_role: Optional[str]) -> str:
    labels: dict[str, str] = {
        "tank_outlet":      "saída da caixa (contador 2)",
        "street_inlet":     "entrada de água da rua (contador 1)",
        "tank_pressure":    "pressão da caixa",
        "street":           "pressão da rua",
        "street_pressure":  "pressão da rua",
        "tank_sensor":      "sensor da caixa",
        "level":            "nível da caixa",
        "communication":    "comunicação",
    }
    return labels.get(channel_role or "", channel_role or "canal monitorado")


def _build_interpretation(
    rule_key: str,
    dr: Optional[dict[str, Any]],
    mensagem_usuario: Optional[str],
) -> tuple[str, bool]:
    """Retorna (texto_interpretação, dados_suficientes)."""
    safe_dr: dict[str, Any] = dr or {}

    # ── sem_comunicacao — tem dados suficientes sempre ──────────────────────
    if rule_key == "sem_comunicacao":
        age = safe_dr.get("age_minutes")
        ultima = safe_dr.get("ultima_leitura") or safe_dr.get("event_time")
        if age is not None:
            hours = float(age) / 60
            age_str = f"{hours:.1f}h" if hours >= 1 else f"{int(age)} min"
        else:
            age_str = "um período prolongado"
        ultima_str = f" Última leitura: {ultima}." if ultima else ""
        return (
            f"O alerta foi gerado porque a instalação ficou sem comunicação por {age_str}. "
            f"O dispositivo não está enviando dados de telemetria.{ultima_str}",
            True,
        )

    # ── sensor_invalido ───────────────────────────────────────────────────────
    if rule_key == "sensor_invalido":
        anomalias = safe_dr.get("anomalias", [])
        if anomalias:
            anom_str = ", ".join(str(a) for a in anomalias)
            return (
                f"O alerta foi gerado porque foram detectados valores fisicamente impossíveis "
                f"nos sensores: {anom_str}. "
                "Isso indica possível falha de sensor ou erro de calibração.",
                True,
            )

    reason = safe_dr.get("reason")

    # ── Detectores do novo motor (com reason) ─────────────────────────────────
    if reason == "pressure2_zero_temperature2_zero":
        p2 = safe_dr.get("pressure2", 0)
        t2 = safe_dr.get("temperature2", 0)
        pts = safe_dr.get("points_confirming")
        pts_str = f" A condição persistiu por {pts} leituras consecutivas." if pts else ""
        return (
            f"O alerta foi gerado porque a pressão da caixa ({p2} MCA) e a temperatura 2 "
            f"({t2} °C) ficaram zeradas em leituras consecutivas. "
            f"Isso indica provável falha no sensor da caixa, cabo, alimentação ou conexão.{pts_str}",
            True,
        )

    if reason == "pressure2_zero_temperature2_valid":
        p2 = safe_dr.get("pressure2", 0)
        t2 = safe_dr.get("temperature2")
        pts = safe_dr.get("points_confirming")
        t2_str = f"{float(t2):.1f} °C" if t2 is not None else "valor normal"
        pts_str = f" A condição persistiu por {pts} leituras consecutivas." if pts else ""
        return (
            f"O alerta foi gerado porque a pressão da caixa ficou zerada ({p2} MCA), "
            f"mas o sensor continuou respondendo temperatura ({t2_str}). "
            f"Isso indica que o sensor está funcionando, mas a caixa pode estar sem água ou sem pressão.{pts_str}",
            True,
        )

    if reason == "sustained_flow_above_installation_reference":
        obs      = safe_dr.get("observed_value")
        unit     = safe_dr.get("observed_unit", "L/h")
        channel  = safe_dr.get("channel_role", "")
        normal_h = safe_dr.get("normal_high")
        anomaly_h = safe_dr.get("anomaly_high")
        period   = safe_dr.get("period_type", "overall")
        conf     = safe_dr.get("baseline_confidence")
        channel_label = _channel_role_label(channel)
        _PERIOD_LABELS = {
            "overall": "geral", "night": "noturno", "day": "diurno",
            "business_hours": "horário comercial", "off_hours": "fora do expediente",
            "weekend": "fim de semana",
        }
        period_label = _PERIOD_LABELS.get(period, period)
        obs_str = f"{float(obs):.1f} {unit}" if obs is not None else "valor elevado"
        bounds_str = ""
        if normal_h is not None and anomaly_h is not None:
            bounds_str = (
                f" Padrão {period_label} desta instalação: "
                f"normal ≤ {float(normal_h):.1f} {unit}, "
                f"anomalia > {float(anomaly_h):.1f} {unit}."
            )
        elif anomaly_h is not None:
            bounds_str = f" Limite de anomalia desta instalação: {float(anomaly_h):.1f} {unit}."
        conf_str = f" Confiança da baseline: {conf}." if conf else ""
        sev_block = _severity_detail_block(safe_dr)
        return (
            f"O alerta foi gerado porque {channel_label} ficou acima do padrão desta instalação "
            f"no período {period_label}. Valor observado: {obs_str}.{bounds_str}{conf_str}{sev_block}",
            True,
        )

    if reason == "flow_peak_short_window":
        obs      = safe_dr.get("observed_value")
        unit     = safe_dr.get("observed_unit", "L/h")
        channel  = safe_dr.get("channel_role", "")
        normal_h = safe_dr.get("normal_high")
        anomaly_h = safe_dr.get("anomaly_high")
        channel_label = _channel_role_label(channel)
        obs_str = f"{float(obs):.1f} {unit}" if obs is not None else "valor elevado"
        bounds_str = ""
        if normal_h is not None and anomaly_h is not None:
            bounds_str = (
                f" Padrão desta instalação: "
                f"normal ≤ {float(normal_h):.1f} {unit}, "
                f"anomalia > {float(anomaly_h):.1f} {unit}."
            )
        sev_block = _severity_detail_block(safe_dr)
        return (
            f"O alerta foi gerado por um pico de consumo em {channel_label}. "
            f"Valor observado: {obs_str}.{bounds_str} "
            f"Este é um alerta de baixa severidade — representa um pico breve, não uma anomalia sustentada.{sev_block}",
            True,
        )

    if reason == "night_flow_elevated":
        obs      = safe_dr.get("observed_value")
        unit     = safe_dr.get("observed_unit", "L/h")
        channel  = safe_dr.get("channel_role", "")
        normal_h = safe_dr.get("normal_high")
        anomaly_h = safe_dr.get("anomaly_high")
        conf     = safe_dr.get("baseline_confidence")
        channel_label = _channel_role_label(channel)
        obs_str = f"{float(obs):.1f} {unit}" if obs is not None else "acima do esperado"
        bounds_str = ""
        if normal_h is not None and anomaly_h is not None:
            bounds_str = (
                f" Padrão noturno desta instalação: "
                f"normal ≤ {float(normal_h):.1f} {unit}, "
                f"anomalia > {float(anomaly_h):.1f} {unit}."
            )
        conf_str = f" Confiança da baseline: {conf}." if conf else ""
        sev_block = _severity_detail_block(safe_dr)
        return (
            f"O alerta foi gerado porque {channel_label} apresentou fluxo elevado "
            f"durante o período noturno (00h–05h). Valor médio noturno: {obs_str}.{bounds_str}{conf_str} "
            f"Consumo noturno elevado em prédio público pode indicar uso irregular ou vazamento.{sev_block}",
            True,
        )

    if reason == "outlet_continuous_tank_falling":
        obs      = safe_dr.get("observed_value")
        unit     = safe_dr.get("observed_unit", "L/h")
        normal_h = safe_dr.get("normal_high")
        anomaly_h = safe_dr.get("anomaly_high")
        conf     = safe_dr.get("baseline_confidence")
        obs_str = f"{float(obs):.1f} {unit}" if obs is not None else "acima do normal"
        bounds_str = ""
        if normal_h is not None:
            bounds_str += f" Normal desta instalação: ≤ {float(normal_h):.1f} {unit}."
        if anomaly_h is not None:
            bounds_str += f" Anomalia: > {float(anomaly_h):.1f} {unit}."
        conf_str = f" Confiança da baseline: {conf}." if conf else ""
        sev_block = _severity_detail_block(safe_dr)
        return (
            f"O alerta foi gerado porque a saída da caixa ({obs_str}) permaneceu acima "
            f"do padrão desta instalação com a pressão/nível da caixa em queda — "
            f"evidência composta de possível vazamento.{bounds_str}{conf_str}{sev_block}",
            True,
        )

    if reason == "street_pressure_below_reference":
        obs = safe_dr.get("observed_value")
        ref = safe_dr.get("baseline_value")
        unit = safe_dr.get("observed_unit", "MCA")
        obs_str = f"{float(obs):.2f} {unit}" if obs is not None else "abaixo do normal"
        ref_str = f"{float(ref):.2f} {unit}" if ref is not None else "referência histórica"
        return (
            f"O alerta foi gerado porque a pressão da rua ficou abaixo da referência "
            f"histórica desta instalação. Pressão observada: {obs_str}; "
            f"referência: {ref_str}. A condição foi sustentada durante a janela analisada.",
            True,
        )

    if reason == "velocity_above_typical":
        channel   = safe_dr.get("channel_role", "")
        unit      = safe_dr.get("observed_unit", "")
        mult      = safe_dr.get("velocity_multiple")
        recent    = safe_dr.get("recent_variation_per_hour")
        typ       = safe_dr.get("typical_variation_per_hour")
        direction = safe_dr.get("direction")
        cur       = safe_dr.get("current_value")
        conf      = safe_dr.get("baseline_confidence")
        channel_label = _channel_role_label(channel)
        sentido = "subiu" if direction == "alta" else "caiu"
        mult_str = f"{float(mult):.1f}×" if mult is not None else "muito"
        rate_str = ""
        if recent is not None and typ is not None:
            rate_str = (
                f" Variou {float(recent):.1f} {unit}/h, contra um típico de "
                f"{float(typ):.1f} {unit}/h nesta instalação."
            )
        cur_str = f" Valor atual: {float(cur):.1f} {unit}." if cur is not None else ""
        conf_str = f" Confiança da baseline: {conf}." if conf else ""
        return (
            f"O alerta foi gerado porque {channel_label} {sentido} muito mais rápido que o "
            f"normal desta instalação ({mult_str} a velocidade típica).{rate_str}{cur_str}{conf_str}",
            True,
        )

    if reason == "flow_below_anomaly_low_continuous":
        obs       = safe_dr.get("observed_value")
        unit      = safe_dr.get("observed_unit", "L/h")
        anomaly_l = safe_dr.get("anomaly_low")
        deficit   = safe_dr.get("deficit_below_anomaly")
        channel   = safe_dr.get("channel_role", "")
        conf      = safe_dr.get("baseline_confidence")
        channel_label = _channel_role_label(channel)
        obs_str = f"{float(obs):.1f} {unit}" if obs is not None else "muito baixo"
        bounds_str = ""
        if anomaly_l is not None:
            bounds_str = f" Limite inferior desta instalação: {float(anomaly_l):.1f} {unit}."
        deficit_str = f" Déficit: {float(deficit):.1f} {unit}." if deficit is not None else ""
        conf_str = f" Confiança da baseline: {conf}." if conf else ""
        return (
            f"O alerta foi gerado porque {channel_label} ficou anormalmente BAIXO para um "
            f"fluxo que normalmente é contínuo nesta instalação. Valor observado: {obs_str}."
            f"{bounds_str}{deficit_str} Pode indicar interrupção de fornecimento, registro "
            f"fechado ou falha de medição.{conf_str}",
            True,
        )

    # ── Detectores do motor antigo (sem reason — campos legados) ──────────────
    if rule_key == "consumo_acima_media":
        flow_atual = safe_dr.get("flow_atual_lph")
        baseline_lph = safe_dr.get("baseline_lph")
        ratio = safe_dr.get("ratio")
        if flow_atual is not None and baseline_lph is not None:
            ratio_str = f" ({float(ratio):.1f}× a média)" if ratio else ""
            return (
                f"O alerta foi gerado porque a vazão ({float(flow_atual):.0f} L/h) ficou acima "
                f"da média histórica desta instalação ({float(baseline_lph):.0f} L/h){ratio_str}.",
                True,
            )

    if rule_key == "pico_consumo":
        flow_atual = safe_dr.get("flow_atual_lph")
        ref_mean = safe_dr.get("ref_mean_lph")
        ratio = safe_dr.get("ratio")
        if flow_atual is not None and ref_mean is not None:
            ratio_str = f" ({float(ratio):.1f}×)" if ratio else ""
            return (
                f"O alerta foi gerado por um pico de consumo: vazão {float(flow_atual):.0f} L/h "
                f"vs média recente de {float(ref_mean):.0f} L/h{ratio_str}.",
                True,
            )

    if rule_key == "vazao_noturna":
        night_mean = safe_dr.get("night_mean_lph")
        baseline_lph = safe_dr.get("baseline_lph")
        ratio = safe_dr.get("night_ratio")
        if night_mean is not None:
            ref_str = f" (referência diária: {float(baseline_lph):.0f} L/h)" if baseline_lph else ""
            pct_str = f" — {float(ratio) * 100:.0f}% da média" if ratio else ""
            return (
                f"O alerta foi gerado porque o fluxo noturno (00h–05h) foi de "
                f"{float(night_mean):.0f} L/h{pct_str}{ref_str}. "
                "Consumo noturno elevado em prédio público pode indicar uso irregular ou vazamento.",
                True,
            )

    if rule_key == "consumo_sem_repouso":
        janela = safe_dr.get("janela_horas")
        flow_atual = safe_dr.get("flow_atual_lph")
        if janela:
            flow_str = f" Fluxo atual: {float(flow_atual):.0f} L/h." if flow_atual else ""
            return (
                f"O alerta foi gerado porque não houve pausa no consumo por {janela}h consecutivas.{flow_str} "
                "Consumo ininterrupto pode indicar vazamento ou torneira aberta.",
                True,
            )

    if rule_key == "behavior_baseline_stale":
        age = safe_dr.get("age_hours")
        last_at = safe_dr.get("last_computed_at")
        thr = safe_dr.get("threshold_hours", 26)
        if age is not None:
            last_str = f" Último cálculo: {last_at}." if last_at else ""
            return (
                f"O baseline comportamental desta instalação não foi recalculado há "
                f"{float(age):.0f}h (limite operacional: {thr}h). "
                f"O timer diário do behavior_baseline_worker pode estar com problema.{last_str}",
                True,
            )

    if rule_key == "nivel_baixo":
        level = safe_dr.get("level_pct")
        if level is not None:
            return (
                f"O alerta foi gerado porque o nível do reservatório ficou em {float(level):.1f}%, "
                "abaixo do limite configurado. Reabastecimento necessário.",
                True,
            )

    if rule_key == "autonomia_insuficiente":
        dias = safe_dr.get("autonomia_dias")
        if dias is not None:
            dias_f = float(dias)
            time_str = f"{dias_f * 24:.1f}h" if dias_f < 1 else f"{dias_f:.1f} dias"
            return (
                f"O alerta foi gerado porque a autonomia estimada do reservatório caiu para {time_str} "
                "ao consumo atual. Planejar reabastecimento.",
                True,
            )

    if rule_key == "queda_nivel":
        queda = safe_dr.get("queda_pct_por_hora")
        level = safe_dr.get("level_pct_atual")
        if queda is not None:
            level_str = f" (nível atual: {float(level):.1f}%)" if level is not None else ""
            return (
                f"O alerta foi gerado porque o nível da caixa está caindo a "
                f"{float(queda):.1f} p.p./hora{level_str}. "
                "Queda acelerada pode indicar vazamento ou consumo anormal.",
                True,
            )

    # Fallback: mensagem_usuario como melhor esforço
    if mensagem_usuario:
        return (mensagem_usuario, False)

    return (
        "Este alerta foi registrado, mas ainda não há evidência detalhada suficiente "
        "para reconstruir toda a decisão.",
        False,
    )


def _caps_to_audit(caps: InstallationCapabilities) -> AuditCapabilities:
    return AuditCapabilities(
        confidence=caps.confidence,
        sample_count=caps.sample_count,
        has_street_pressure=caps.has_street_pressure,
        has_tank_pressure=caps.has_tank_pressure,
        has_temperature2=caps.has_temperature2,
        has_street_inlet_counter=caps.has_street_inlet_counter,
        has_tank_outlet_counter=caps.has_tank_outlet_counter,
        can_alert_street_pressure=caps.can_alert_street_pressure,
        can_alert_tank=caps.can_alert_tank,
        can_alert_tank_sensor=caps.can_alert_tank_sensor,
        can_alert_level=caps.can_alert_level,
        can_alert_flow_inlet=caps.can_alert_flow_inlet,
        can_alert_flow_outlet=caps.can_alert_flow_outlet,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/audit", response_model=AuditResponse)
async def get_alerts_audit(
    user: CurrentUser,
    db: DbDep,
    from_dt: Optional[datetime] = Query(None, alias="from"),
    to_dt: Optional[datetime] = Query(None, alias="to"),
    installation_slug: Optional[str] = Query(None),
    status: str = Query("all"),          # active | resolved | all
    severity: Optional[str] = Query(None),
    rule_key: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """
    Relatório de auditoria dos alertas gerados.
    Agrupa eventos por instalação e inclui interpretação em linguagem humana.
    """
    now_utc = datetime.now(timezone.utc)

    # Default lookback: 24h na listagem geral.
    # Consulta pontual do modal (slug + rule_key sem from) usa janela ampla
    # para encontrar alertas ativos há mais de 24h.
    if from_dt is None:
        if installation_slug is not None and rule_key is not None:
            from_dt = now_utc - timedelta(days=90)
        else:
            from_dt = now_utc - timedelta(hours=24)

    # Garantir timezone-aware
    if from_dt.tzinfo is None:
        from_dt = from_dt.replace(tzinfo=timezone.utc)
    if to_dt is not None and to_dt.tzinfo is None:
        to_dt = to_dt.replace(tzinfo=timezone.utc)

    # Mapear status para valor PT do banco
    status_map = {"active": "ativo", "resolved": "resolvido"}
    status_pt = status_map.get(status)  # None = sem filtro (all)

    # Construir WHERE dinâmico
    clauses: list[str] = ["ae.triggered_at >= :from_dt"]
    params: dict[str, Any] = {
        "from_dt": from_dt,
        "limit": limit,
        "offset": offset,
    }

    if to_dt is not None:
        clauses.append("ae.triggered_at <= :to_dt")
        params["to_dt"] = to_dt

    if status_pt is not None:
        clauses.append("ae.status = :status_pt")
        params["status_pt"] = status_pt

    if installation_slug is not None:
        clauses.append("i.slug = :slug")
        params["slug"] = installation_slug

    if severity is not None:
        clauses.append("ae.severity = :severity")
        params["severity"] = severity

    if rule_key is not None:
        clauses.append("ae.rule_key = :rule_key_filter")
        params["rule_key_filter"] = rule_key

    where_clause = "WHERE " + " AND ".join(clauses)

    sql_audit = text(f"""
        SELECT
            ae.id               AS event_id,
            ae.installation_id,
            i.slug              AS installation_slug,
            i.name              AS installation_name,
            ae.rule_key,
            ae.alert_type,
            ae.severity,
            ae.titulo,
            ae.mensagem_usuario,
            ae.recomendacao,
            ae.dados_relevantes,
            ae.status,
            ae.current_value,
            ae.triggered_at,
            ae.resolved_at,
            ae.updated_at,
            als.is_active,
            als.first_triggered_at,
            als.last_triggered_at
        FROM alert_events ae
        JOIN installations i ON i.id = ae.installation_id
        LEFT JOIN alert_state als
            ON als.installation_id = ae.installation_id
           AND als.rule_key = ae.rule_key
        {where_clause}
        ORDER BY ae.installation_id, ae.triggered_at DESC
        LIMIT :limit OFFSET :offset
    """)

    rows = (await db.execute(sql_audit, params)).fetchall()

    # Agrupar por instalação
    inst_map: dict[int, dict[str, Any]] = {}
    inst_order: list[int] = []

    for row in rows:
        inst_id = row.installation_id
        if inst_id not in inst_map:
            inst_map[inst_id] = {
                "installation_id": inst_id,
                "slug": row.installation_slug,
                "name": row.installation_name,
                "events": [],
            }
            inst_order.append(inst_id)
        inst_map[inst_id]["events"].append(row)

    # Montar resposta por instalação
    installations_out: list[AuditInstallation] = []
    total_active = 0
    total_resolved = 0
    total_critical = 0

    for inst_id in inst_order:
        data = inst_map[inst_id]
        caps = await get_installation_capabilities(
            inst_id, db, slug=data["slug"]
        )

        audit_alerts: list[AuditAlert] = []
        inst_active = 0
        inst_resolved = 0

        for ev in data["events"]:
            dr: dict[str, Any] = ev.dados_relevantes or {}
            interp, data_suf = _build_interpretation(
                ev.rule_key, dr, ev.mensagem_usuario
            )

            channel_role = dr.get("channel_role")

            # is_active: preferir alert_state (estado atual); fallback = status do evento
            is_active = bool(ev.is_active) if ev.is_active is not None else (ev.status == "ativo")

            # from_legacy_engine: evento gerado pelo motor antigo (sem reason nem channel_role)
            from_legacy = (dr.get("reason") is None and dr.get("channel_role") is None
                           and ev.rule_key not in ("sem_comunicacao", "sensor_invalido"))

            audit_alerts.append(AuditAlert(
                event_id=ev.event_id,
                rule_key=ev.rule_key,
                titulo=ev.titulo,
                severity=ev.severity,
                status=ev.status,
                is_active=is_active,
                triggered_at=_ts_z(ev.triggered_at) or "",
                resolved_at=_ts_z(ev.resolved_at),
                first_triggered_at=_ts_z(ev.first_triggered_at),
                last_triggered_at=_ts_z(ev.last_triggered_at),
                evidence_time=dr.get("evidence_time"),
                window_start_at=dr.get("window_start_at"),
                window_end_at=dr.get("window_end_at"),
                metric_used=dr.get("metric_used"),
                channel_role=channel_role,
                channel_role_label=_channel_role_label(channel_role),
                observed_value=_safe_float(dr.get("observed_value")),
                observed_unit=dr.get("observed_unit"),
                baseline_metric=dr.get("baseline_metric"),
                baseline_value=_safe_float(dr.get("baseline_value")),
                threshold_value=_safe_float(dr.get("threshold_value")),
                absolute_floor=_safe_float(dr.get("absolute_floor")),
                sample_count_ref=_safe_int(dr.get("sample_count")),
                points_above_threshold=_safe_int(dr.get("points_above_threshold")),
                window_points=_safe_int(dr.get("window_points")),
                points_confirming=_safe_int(dr.get("points_confirming")),
                reason=dr.get("reason"),
                normal_high=_safe_float(dr.get("normal_high")),
                anomaly_high=_safe_float(dr.get("anomaly_high")),
                baseline_confidence=dr.get("baseline_confidence"),
                period_type=dr.get("period_type"),
                profile_type=dr.get("profile_type"),
                excess_over_normal=_safe_float(dr.get("excess_over_normal")),
                excess_over_normal_pct=_safe_float(dr.get("excess_over_normal_pct")),
                excess_over_anomaly=_safe_float(dr.get("excess_over_anomaly")),
                excess_over_anomaly_pct=_safe_float(dr.get("excess_over_anomaly_pct")),
                severity_reason=dr.get("severity_reason"),
                composite_evidence=bool(dr.get("composite_evidence", False)),
                strong_composite_evidence=bool(dr.get("strong_composite_evidence", False)),
                composite_evidence_factors=list(dr.get("composite_evidence_factors") or []),
                duration_minutes=_safe_float(dr.get("duration_minutes")),
                interpretation=interp,
                data_sufficient=data_suf,
                from_legacy_engine=from_legacy,
                dados_relevantes=dr or None,
                current_value=_safe_float(ev.current_value),
                mensagem_usuario=ev.mensagem_usuario,
                recomendacao=ev.recomendacao,
            ))

            # Contagens por estado ATUAL (is_active), não por status do evento histórico
            if is_active:
                inst_active += 1
                total_active += 1
            else:
                inst_resolved += 1
                total_resolved += 1
            if ev.severity == "critico":
                total_critical += 1

        installations_out.append(AuditInstallation(
            installation_id=inst_id,
            slug=data["slug"],
            name=data["name"],
            capabilities=_caps_to_audit(caps),
            alerts=audit_alerts,
            total_active=inst_active,
            total_resolved=inst_resolved,
        ))

    total_alerts = total_active + total_resolved
    summary = AuditSummary(
        total_alerts=total_alerts,
        active_alerts=total_active,
        resolved_alerts=total_resolved,
        critical_alerts=total_critical,
        installations_with_alerts=len(installations_out),
    )

    return AuditResponse(
        generated_at=_ts_z(now_utc) or "",
        from_dt=_ts_z(from_dt),
        to_dt=_ts_z(to_dt),
        summary=summary,
        installations=installations_out,
    )


def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(v: Any) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


@router.get("", response_model=AlertsResponse)
async def get_alerts(
    user: CurrentUser,
    db: DbDep,
    installation_slug: str | None = Query(None),
    active_only: bool = Query(True),
):
    states_clauses: list[str] = []
    events_clauses: list[str] = []
    user_id = _current_user_id(user)
    params: dict[str, object] = {"user_id": user_id}

    if installation_slug is not None:
        states_clauses.append("i.slug = :slug")
        events_clauses.append("i.slug = :slug")
        params["slug"] = installation_slug

    if active_only:
        states_clauses.append("als.is_active = true")

    states_where = ("WHERE " + " AND ".join(states_clauses)) if states_clauses else ""
    events_where = ("WHERE " + " AND ".join(events_clauses)) if events_clauses else ""

    states_result = await db.execute(
        text(_SQL_STATES.format(states_where=states_where)), params
    )
    events_result = await db.execute(
        text(_SQL_EVENTS.format(events_where=events_where)), params
    )

    now = datetime.now(timezone.utc)
    inst_statuses: dict[str, InstallationStatusOut] = {}
    states: list[AlertStateOut] = []

    for row in states_result.fetchall():
        slug = row.installation_slug
        states.append(
            AlertStateOut(
                installation_slug=slug,
                rule_key=row.rule_key,
                alert_type=row.alert_type,
                severity=row.severity,
                is_active=row.is_active,
                current_value=row.current_value,
                first_triggered_at=_ts_z(row.first_triggered_at),
                last_triggered_at=_ts_z(row.last_triggered_at),
                last_resolved_at=_ts_z(row.last_resolved_at),
                titulo=row.titulo,
                mensagem_usuario=row.mensagem_usuario,
                recomendacao=row.recomendacao,
                dados_relevantes=row.dados_relevantes,
                viewed_by_user=bool(row.viewed_by_user),
            )
        )
        if slug not in inst_statuses:
            lmu = row.inst_learning_mode_until
            bra = row.inst_baseline_ready_at
            inst_statuses[slug] = InstallationStatusOut(
                environment=row.inst_environment or "production",
                learning_mode_until=_ts_z(lmu),
                baseline_ready_at=_ts_z(bra),
                is_learning=bool(lmu and lmu > now),
                has_baseline=bra is not None,
            )

    events = [
        AlertEventOut(
            installation_slug=row.installation_slug,
            rule_key=row.rule_key,
            alert_type=row.alert_type,
            severity=row.severity,
            message=row.message,
            status=row.status,
            current_value=row.current_value,
            triggered_at=_ts_z(row.triggered_at),
            titulo=row.titulo,
            mensagem_usuario=row.mensagem_usuario,
            recomendacao=row.recomendacao,
            dados_relevantes=row.dados_relevantes,
        )
        for row in events_result.fetchall()
    ]

    return AlertsResponse(states=states, recent_events=events,
                          installation_statuses=inst_statuses)


@router.post("/{installation_slug}/{rule_key}/viewed", status_code=204)
async def mark_viewed(
    user: CurrentUser,
    db: DbDep,
    installation_slug: str,
    rule_key: str,
):
    """Marca um alerta como visto pelo usuário autenticado (idempotente)."""
    inst_result = await db.execute(_SQL_GET_INST_ID, {"slug": installation_slug})
    inst_id = inst_result.scalar()
    if inst_id is None:
        raise HTTPException(status_code=404, detail="Instalação não encontrada")

    user_id = _current_user_id(user)
    await db.execute(
        _SQL_UPSERT_VIEW,
        {"installation_id": inst_id, "rule_key": rule_key, "user_id": user_id},
    )
    await db.commit()


@router.delete("/{installation_slug}/{rule_key}/viewed", status_code=204)
async def unmark_viewed(
    user: CurrentUser,
    db: DbDep,
    installation_slug: str,
    rule_key: str,
):
    """Remove o registro de "visto" para o alerta."""
    inst_result = await db.execute(_SQL_GET_INST_ID, {"slug": installation_slug})
    inst_id = inst_result.scalar()
    if inst_id is None:
        raise HTTPException(status_code=404, detail="Instalação não encontrada")

    user_id = _current_user_id(user)
    await db.execute(
        _SQL_DELETE_VIEW,
        {"installation_id": inst_id, "rule_key": rule_key, "user_id": user_id},
    )
    await db.commit()
