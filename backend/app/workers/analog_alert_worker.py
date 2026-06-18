"""
app/workers/analog_alert_worker.py — Motor de alertas analógico (Hospital Santa Ana).

Ciclo (a cada worker_alert_interval_seconds):
  1. Carrega todos os devices registrados (device_installations.valid_to IS NULL).
  2. Para cada device executa o pipeline (transação isolada):
     a. detect_stale        — telemetria parada por device registrado
     b. detect_sensor_fault — undercurrent / overrange sustentado (com histerese)
     c. detect_level_low    — nível abaixo de threshold (requer can_alert_level)
     d. detect_level_high   — nível acima de threshold (requer can_alert_level)
     e. detect_battery_low  — bateria baixa
     f. detect_signal_low   — sinal ruim
  3. Upsert alert_state + alert_events em transições.

Regras:
  - alert_state e alert_events incluem device_id (per-device, não só per-instalação).
  - Stale é determinado pelo silêncio do device — independe de capabilities.
  - Sem pressão, vazão, calibração ou baselines comportamentais.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.device_capabilities import (
    DeviceCapabilities,
    get_device_capabilities,
)
from app.config import get_settings
from app.db.session import get_session
from app.logging import get_logger
from app.services.alert_notification_service import (
    enqueue_critical_alert_user_notifications,
)
from app.workers.alert_trigger import drain_dirty as _drain_dirty

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_BATTERY_LOW_V: float = 3.2
_BATTERY_CRITICAL_V: float = 3.0
_SIGNAL_LOW_DBM: float = -110.0
_SIGNAL_CRITICAL_DBM: float = -120.0
_LEVEL_CRITICAL_PCT: float = 25.0
_LEVEL_WARNING_PCT: float = 60.0

# Janela de série (h) para detecção de sensor_fault sustentado
_SERIES_HOURS: int = 4


# ---------------------------------------------------------------------------
# Tipos internos
# ---------------------------------------------------------------------------

@dataclass
class SeriesPoint:
    ts: datetime
    value: float


@dataclass
class DeviceContext:
    """Dados para avaliar detectores de um device."""
    device_id: int
    installation_id: int
    installation_slug: str
    imei: str
    label: Optional[str]
    model: str
    series: dict[str, list[SeriesPoint]] = field(default_factory=dict)
    latest_ts: Optional[datetime] = None
    capabilities: Optional[DeviceCapabilities] = None
    prior_states: dict[str, dict] = field(default_factory=dict)


@dataclass
class DetectorResult:
    rule_key: str
    alert_type: str
    is_active: bool
    device_id: int
    severity: Optional[str] = None
    titulo: Optional[str] = None
    mensagem_usuario: Optional[str] = None
    recomendacao: Optional[str] = None
    dados_relevantes: Optional[dict[str, Any]] = None
    current_value: Optional[float] = None
    reason: Optional[str] = None


def _inactive(rule_key: str, alert_type: str, device_id: int, reason: str) -> DetectorResult:
    return DetectorResult(
        rule_key=rule_key, alert_type=alert_type,
        is_active=False, device_id=device_id, reason=reason,
    )


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_SQL_REGISTERED_DEVICES = text("""
    SELECT
        d.id   AS device_id,
        d.imei,
        d.label,
        d.model,
        di.installation_id,
        i.slug  AS installation_slug
    FROM devices d
    JOIN device_installations di ON di.device_id = d.id AND di.valid_to IS NULL
    JOIN installations i ON i.id = di.installation_id
    WHERE d.is_active = true
    ORDER BY d.id
""")

_SQL_SERIES = text("""
    SELECT metric_name, value, derived_at_utc
    FROM derived_metrics
    WHERE device_id = :device_id
      AND metric_name IN ('current_ma', 'level_pct', 'level_m', 'voltage_v', 'battery_v', 'signal')
      AND derived_at_utc >= now() - :hours * INTERVAL '1 hour'
    ORDER BY metric_name, derived_at_utc ASC
""")

_SQL_LATEST_TS = text("""
    SELECT MAX(collected_at_utc) FROM parsed_measurements WHERE device_id = :device_id
""")

_SQL_STATES = text("""
    SELECT rule_key, is_active, first_triggered_at, last_triggered_at,
           last_resolved_at, current_value, severity, dados_relevantes
    FROM alert_state
    WHERE installation_id = :installation_id
      AND device_id = :device_id
""")

_SQL_UPSERT_STATE = text("""
    INSERT INTO alert_state (
        installation_id, device_id, rule_key, is_active,
        alert_type, severity, titulo, mensagem_usuario, recomendacao,
        dados_relevantes, current_value,
        first_triggered_at, last_triggered_at, last_resolved_at,
        updated_at
    ) VALUES (
        :installation_id, :device_id, :rule_key, :is_active,
        :alert_type, :severity, :titulo, :mensagem_usuario, :recomendacao,
        CAST(:dados_relevantes AS jsonb), :current_value,
        :first_triggered_at, :last_triggered_at, :last_resolved_at,
        now()
    )
    ON CONFLICT (installation_id, device_id, rule_key) WHERE device_id IS NOT NULL
    DO UPDATE SET
        is_active           = EXCLUDED.is_active,
        alert_type          = EXCLUDED.alert_type,
        severity            = CASE WHEN EXCLUDED.is_active THEN EXCLUDED.severity
                                   ELSE alert_state.severity END,
        titulo              = CASE WHEN EXCLUDED.is_active THEN EXCLUDED.titulo
                                   ELSE alert_state.titulo END,
        mensagem_usuario    = CASE WHEN EXCLUDED.is_active THEN EXCLUDED.mensagem_usuario
                                   ELSE alert_state.mensagem_usuario END,
        recomendacao        = CASE WHEN EXCLUDED.is_active THEN EXCLUDED.recomendacao
                                   ELSE alert_state.recomendacao END,
        dados_relevantes    = CASE WHEN EXCLUDED.is_active THEN EXCLUDED.dados_relevantes
                                   ELSE alert_state.dados_relevantes END,
        current_value       = EXCLUDED.current_value,
        first_triggered_at  = CASE
            WHEN EXCLUDED.is_active
                 AND (NOT alert_state.is_active OR alert_state.first_triggered_at IS NULL)
            THEN EXCLUDED.first_triggered_at
            ELSE alert_state.first_triggered_at
        END,
        last_triggered_at   = CASE
            WHEN EXCLUDED.is_active THEN EXCLUDED.last_triggered_at
            ELSE alert_state.last_triggered_at
        END,
        last_resolved_at    = CASE
            WHEN NOT EXCLUDED.is_active AND alert_state.is_active THEN now()
            ELSE alert_state.last_resolved_at
        END,
        updated_at          = now()
""")

_SQL_INSERT_EVENT = text("""
    INSERT INTO alert_events (
        installation_id, device_id, rule_key, alert_type, severity,
        message, titulo, mensagem_usuario, recomendacao,
        dados_relevantes, status, current_value, triggered_at
    ) VALUES (
        :installation_id, :device_id, :rule_key, :alert_type, :severity,
        :message, :titulo, :mensagem_usuario, :recomendacao,
        CAST(:dados_relevantes AS jsonb), :status, :current_value, now()
    )
    RETURNING id
""")

_SQL_CLOSE_EVENT = text("""
    UPDATE alert_events
    SET status = 'resolvido', updated_at = now()
    WHERE installation_id = :installation_id
      AND device_id = :device_id
      AND rule_key = :rule_key
      AND status = 'ativo'
""")


# ---------------------------------------------------------------------------
# Detectores
# ---------------------------------------------------------------------------

def detect_stale(ctx: DeviceContext, now: datetime, s: Any) -> DetectorResult:
    """Telemetria parada — device registrado sem dados por mais de stale_minutes."""
    rule_key = "stale"
    alert_type = "sem_comunicacao"
    device_id = ctx.device_id

    stale_minutes: float = float(
        s.analog_profiles.get(ctx.model, {}).get(
            "stale_minutes",
            getattr(s, "worker_alert_interval_seconds", 120),
        )
    )
    # Usa alert_defaults de YAML se disponível
    ad = _load_client_yaml_alert_defaults(s)
    stale_minutes = float(ad.get("telemetry_stale_minutes", stale_minutes))

    if ctx.latest_ts is None:
        return _inactive(rule_key, alert_type, device_id, "no_readings_yet")

    age_minutes = (now - ctx.latest_ts).total_seconds() / 60.0
    if age_minutes > stale_minutes:
        return DetectorResult(
            rule_key=rule_key, alert_type=alert_type, is_active=True,
            device_id=device_id,
            severity="alto",
            titulo=f"Telemetria parada — {ctx.label or ctx.imei}",
            mensagem_usuario=(
                f"Sem dados do device {ctx.label or ctx.imei} "
                f"há {age_minutes:.0f} min (limiar: {stale_minutes:.0f} min)."
            ),
            recomendacao="Verificar conectividade da remota e do broker MQTT.",
            dados_relevantes={"age_minutes": round(age_minutes, 1), "stale_minutes": stale_minutes},
        )
    return _inactive(rule_key, alert_type, device_id, "ok")


def detect_sensor_fault(ctx: DeviceContext, now: datetime, s: Any) -> DetectorResult:
    """Under/overcurrent sustentado — falha do sensor analógico."""
    rule_key = "sensor_fault"
    alert_type = "sensor_fault"
    device_id = ctx.device_id

    cap = ctx.capabilities
    if cap is None or not cap.can_alert_sensor_fault:
        return _inactive(rule_key, alert_type, device_id, "no_current_channel")

    profile = s.analog_profiles.get(ctx.model, {})
    fault_below: float = float(profile.get("fault_below_ma", 4.0))
    fault_above: float = float(profile.get("fault_above_ma", 20.5))
    clear_above: float = float(profile.get("clear_above_ma", 4.1))
    sustained_min: float = float(profile.get("fault_sustained_minutes", 10.0))

    series = ctx.series.get("current_ma", [])
    if not series:
        return _inactive(rule_key, alert_type, device_id, "no_series")

    # Janela de sustentação
    cutoff = now.timestamp() - sustained_min * 60.0
    window = [p for p in series if p.ts.timestamp() >= cutoff]
    if len(window) < 2:
        return _inactive(rule_key, alert_type, device_id, "insufficient_points")

    n_under = sum(1 for p in window if p.value < fault_below)
    n_over = sum(1 for p in window if p.value > fault_above)
    n_total = len(window)

    # Histerese: se alerta ativo, limpar só quando > clear_above
    prior = ctx.prior_states.get(rule_key, {})
    prior_active = prior.get("is_active", False)
    if prior_active:
        # Em alerta — verifica limpeza por histerese
        n_clear = sum(1 for p in window if clear_above <= p.value <= fault_above)
        if n_clear / n_total >= 0.75:
            return _inactive(rule_key, alert_type, device_id, "cleared_hysteresis")

    coverage = 0.75
    fault_kind = None
    if n_under / n_total >= coverage:
        fault_kind = "undercurrent"
    elif n_over / n_total >= coverage:
        fault_kind = "overrange"

    if fault_kind is None:
        return _inactive(rule_key, alert_type, device_id, "no_fault")

    last_ma = series[-1].value
    severity = "alto" if fault_kind == "undercurrent" else "moderado"

    return DetectorResult(
        rule_key=rule_key, alert_type=alert_type, is_active=True,
        device_id=device_id,
        severity=severity,
        titulo=f"Falha de sensor — {ctx.label or ctx.imei}",
        mensagem_usuario=(
            f"Sensor do device {ctx.label or ctx.imei} em estado '{fault_kind}' "
            f"(corrente atual: {last_ma:.2f} mA, esperado: {fault_below}–{fault_above} mA)."
        ),
        recomendacao="Verificar cabeamento e sensor da remota analógica.",
        current_value=last_ma,
        dados_relevantes={
            "fault_kind": fault_kind,
            "current_ma": round(last_ma, 3),
            "fault_below_ma": fault_below,
            "fault_above_ma": fault_above,
            "window_points": n_total,
        },
    )


def detect_level_low(ctx: DeviceContext, now: datetime, s: Any) -> DetectorResult:
    """Nível abaixo dos limiares configurados."""
    rule_key = "nivel_baixo"
    alert_type = "nivel_baixo"
    device_id = ctx.device_id

    cap = ctx.capabilities
    if cap is None or not cap.can_alert_level:
        return _inactive(rule_key, alert_type, device_id, "no_level_capability")

    series = ctx.series.get("level_pct", [])
    if not series:
        return _inactive(rule_key, alert_type, device_id, "no_series")

    ad = _load_client_yaml_alert_defaults(s)
    critical_pct: float = float(ad.get("level_critical_pct", _LEVEL_CRITICAL_PCT))
    warning_pct: float = float(ad.get("level_warning_pct", _LEVEL_WARNING_PCT))

    level_pct = series[-1].value

    if level_pct <= critical_pct:
        severity = "critico"
    elif level_pct <= warning_pct:
        severity = "atencao"
    else:
        return _inactive(rule_key, alert_type, device_id, "level_ok")

    return DetectorResult(
        rule_key=rule_key, alert_type=alert_type, is_active=True,
        device_id=device_id,
        severity=severity,
        titulo=f"Nível baixo — {ctx.label or ctx.imei}",
        mensagem_usuario=f"Nível do reservatório em {level_pct:.1f}%.",
        recomendacao="Verificar abastecimento e consumo do reservatório.",
        current_value=level_pct,
        dados_relevantes={
            "level_pct": round(level_pct, 1),
            "level_critical_pct": critical_pct,
            "level_warning_pct": warning_pct,
        },
    )


def detect_battery_low(ctx: DeviceContext, now: datetime, s: Any) -> DetectorResult:
    """Bateria da remota analógica baixa."""
    rule_key = "bateria_baixa"
    alert_type = "bateria_baixa"
    device_id = ctx.device_id

    cap = ctx.capabilities
    if cap is None or not cap.can_alert_battery:
        return _inactive(rule_key, alert_type, device_id, "no_battery_data")

    series = ctx.series.get("battery_v", [])
    if not series:
        return _inactive(rule_key, alert_type, device_id, "no_series")

    batt_v = series[-1].value
    if batt_v <= _BATTERY_CRITICAL_V:
        severity = "critico"
    elif batt_v <= _BATTERY_LOW_V:
        severity = "moderado"
    else:
        return _inactive(rule_key, alert_type, device_id, "battery_ok")

    return DetectorResult(
        rule_key=rule_key, alert_type=alert_type, is_active=True,
        device_id=device_id,
        severity=severity,
        titulo=f"Bateria baixa — {ctx.label or ctx.imei}",
        mensagem_usuario=f"Bateria da remota {ctx.label or ctx.imei} em {batt_v:.2f}V.",
        recomendacao="Substituir ou recarregar bateria da remota.",
        current_value=batt_v,
        dados_relevantes={"battery_v": round(batt_v, 3)},
    )


def detect_signal_low(ctx: DeviceContext, now: datetime, s: Any) -> DetectorResult:
    """Sinal NB-IoT fraco."""
    rule_key = "sinal_fraco"
    alert_type = "sinal_fraco"
    device_id = ctx.device_id

    cap = ctx.capabilities
    if cap is None or not cap.can_alert_signal:
        return _inactive(rule_key, alert_type, device_id, "no_signal_data")

    series = ctx.series.get("signal", [])
    if not series:
        return _inactive(rule_key, alert_type, device_id, "no_series")

    signal_dbm = series[-1].value
    if signal_dbm <= _SIGNAL_CRITICAL_DBM:
        severity = "alto"
    elif signal_dbm <= _SIGNAL_LOW_DBM:
        severity = "moderado"
    else:
        return _inactive(rule_key, alert_type, device_id, "signal_ok")

    return DetectorResult(
        rule_key=rule_key, alert_type=alert_type, is_active=True,
        device_id=device_id,
        severity=severity,
        titulo=f"Sinal fraco — {ctx.label or ctx.imei}",
        mensagem_usuario=f"Sinal da remota {ctx.label or ctx.imei} em {signal_dbm:.0f} dBm.",
        recomendacao="Verificar posicionamento e antena da remota.",
        current_value=signal_dbm,
        dados_relevantes={"signal_rssi": round(signal_dbm, 1)},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALERT_DEFAULTS_CACHE: Optional[dict] = None


def _load_client_yaml_alert_defaults(s: Any) -> dict:
    global _ALERT_DEFAULTS_CACHE
    if _ALERT_DEFAULTS_CACHE is not None:
        return _ALERT_DEFAULTS_CACHE
    try:
        from app.config import _load_client_yaml
        data = _load_client_yaml(s.client_slug)
        _ALERT_DEFAULTS_CACHE = data.get("alert_defaults", {})
    except Exception:
        _ALERT_DEFAULTS_CACHE = {}
    return _ALERT_DEFAULTS_CACHE


# ---------------------------------------------------------------------------
# Persistência de alertas
# ---------------------------------------------------------------------------

async def _persist_results(
    session: AsyncSession,
    installation_id: int,
    results: list[DetectorResult],
) -> None:
    """Upsert alert_state + insere/fecha alert_events em transições."""
    s = get_settings()

    for r in results:
        dr_json = json.dumps(r.dados_relevantes) if r.dados_relevantes else None
        now = datetime.now(timezone.utc)

        await session.execute(
            _SQL_UPSERT_STATE,
            {
                "installation_id": installation_id,
                "device_id": r.device_id,
                "rule_key": r.rule_key,
                "is_active": r.is_active,
                "alert_type": r.alert_type,
                "severity": r.severity,
                "titulo": r.titulo,
                "mensagem_usuario": r.mensagem_usuario,
                "recomendacao": r.recomendacao,
                "dados_relevantes": dr_json,
                "current_value": r.current_value,
                "first_triggered_at": now if r.is_active else None,
                "last_triggered_at": now if r.is_active else None,
                "last_resolved_at": None,
            },
        )

        if r.is_active:
            event_row = await session.execute(
                _SQL_INSERT_EVENT,
                {
                    "installation_id": installation_id,
                    "device_id": r.device_id,
                    "rule_key": r.rule_key,
                    "alert_type": r.alert_type,
                    "severity": r.severity,
                    "message": r.mensagem_usuario or "",
                    "titulo": r.titulo,
                    "mensagem_usuario": r.mensagem_usuario,
                    "recomendacao": r.recomendacao,
                    "dados_relevantes": dr_json,
                    "status": "ativo",
                    "current_value": r.current_value,
                },
            )
            event_id = event_row.fetchone()

            if s.telegram_alerts_enabled and r.severity in ("alto", "critico"):
                try:
                    await enqueue_critical_alert_user_notifications(
                        session=session,
                        installation_id=installation_id,
                        alert_event_id=event_id[0] if event_id else None,
                        rule_key=r.rule_key,
                        severity=r.severity or "alto",
                        titulo=r.titulo or "",
                        mensagem=r.mensagem_usuario or "",
                    )
                except Exception as exc:
                    logger.warning(
                        "alert_worker.telegram_enqueue_failed",
                        rule_key=r.rule_key,
                        error=str(exc),
                    )
        else:
            await session.execute(
                _SQL_CLOSE_EVENT,
                {
                    "installation_id": installation_id,
                    "device_id": r.device_id,
                    "rule_key": r.rule_key,
                },
            )


# ---------------------------------------------------------------------------
# Pipeline por device
# ---------------------------------------------------------------------------

async def _run_pipeline(
    device_row: Any,
    session: AsyncSession,
    now: datetime,
) -> None:
    s = get_settings()
    device_id = device_row.device_id
    installation_id = device_row.installation_id

    # Carrega série
    series_rows = await session.execute(
        _SQL_SERIES,
        {"device_id": device_id, "hours": _SERIES_HOURS},
    )
    series: dict[str, list[SeriesPoint]] = {}
    for metric_name, value, ts in series_rows.fetchall():
        series.setdefault(metric_name, []).append(SeriesPoint(ts=ts, value=float(value)))

    # Carrega última coleta
    latest_row = await session.execute(_SQL_LATEST_TS, {"device_id": device_id})
    latest_rec = latest_row.fetchone()
    latest_ts: Optional[datetime] = latest_rec[0] if latest_rec else None

    # Carrega estado anterior dos alertas
    states_rows = await session.execute(
        _SQL_STATES,
        {"installation_id": installation_id, "device_id": device_id},
    )
    prior_states: dict[str, dict] = {}
    for row in states_rows.fetchall():
        prior_states[row[0]] = {
            "is_active": row[1],
            "first_triggered_at": row[2],
            "dados_relevantes": row[7],
        }

    # Capabilities
    caps = await get_device_capabilities(device_id, session)

    ctx = DeviceContext(
        device_id=device_id,
        installation_id=installation_id,
        installation_slug=device_row.installation_slug,
        imei=device_row.imei,
        label=device_row.label,
        model=device_row.model or "",
        series=series,
        latest_ts=latest_ts,
        capabilities=caps,
        prior_states=prior_states,
    )

    detectors = [
        detect_stale,
        detect_sensor_fault,
        detect_level_low,
        detect_battery_low,
        detect_signal_low,
    ]

    results = [fn(ctx, now, s) for fn in detectors]

    await _persist_results(session, installation_id, results)
    await session.commit()

    active = [r for r in results if r.is_active]
    if active:
        logger.info(
            "alert_worker.device_alerts_active",
            device_id=device_id,
            imei=ctx.imei,
            rules=[r.rule_key for r in active],
        )


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------

async def run_alert_worker() -> None:
    s = get_settings()
    interval = s.worker_alert_interval_seconds
    logger.info("alert_worker.starting", interval_s=interval)

    while True:
        now = datetime.now(timezone.utc)
        try:
            # Drena fila de instalações marcadas como dirty (prioritárias)
            await _drain_dirty()

            async with get_session() as session:
                device_rows = (
                    await session.execute(_SQL_REGISTERED_DEVICES)
                ).fetchall()

            for device_row in device_rows:
                try:
                    async with get_session() as session:
                        await _run_pipeline(device_row, session, now)
                except Exception as exc:
                    logger.error(
                        "alert_worker.device_pipeline_failed",
                        device_id=device_row.device_id,
                        error=str(exc),
                        exc_info=True,
                    )

        except Exception as exc:
            logger.error("alert_worker.cycle_failed", error=str(exc), exc_info=True)

        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def _main() -> None:
    from app.config import get_settings
    from app.logging import configure_logging

    s = get_settings()
    configure_logging(log_level=s.log_level, log_format=s.log_format)
    await run_alert_worker()


if __name__ == "__main__":
    asyncio.run(_main())
