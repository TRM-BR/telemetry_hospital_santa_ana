"""
app/services/alert_simulation_service.py — Serviço read-only de simulação de alertas históricos.

Reúne a lógica de reconstrução de contexto histórico (extraída do backtest CLI) e adiciona
varredura por período, shadow tagging, dedupe e caps de segurança.

Garantias read-only:
- Abre sessão PostgreSQL própria com SET TRANSACTION READ ONLY.
- Valida SHOW transaction_read_only == 'on' antes de qualquer query de dados.
- Nunca chama _apply_result nem escreve em alert_state/alert_events/baselines.
- ROLLBACK garantido no finally.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.capabilities import get_installation_capabilities
from app.config import get_settings
from app.db.session import _get_session_factory
from app.logging import get_logger
from app.processing.derivations.flow_window import windowed_flow_series
from app.workers.alert_worker import (
    _SHADOW_ONLY_RULES,
    _STALE_HOURS,
    DetectorResult,
    InstallationContext,
    SeriesPoint,
    _run_pipeline,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Caps de segurança
# ---------------------------------------------------------------------------

_MAX_EVALUATIONS = 20_000
_SIMULATION_TIMEOUT_S = 25

# ---------------------------------------------------------------------------
# SQL (versões ancoradas em :as_of — paridade com o worker)
# ---------------------------------------------------------------------------

_SQL_ACTIVE_INSTALLATIONS = text("""
    SELECT DISTINCT i.id, i.slug, i.name
    FROM installations i
    JOIN device_installations di ON di.installation_id = i.id AND di.valid_to IS NULL
    JOIN devices d ON d.id = di.device_id AND d.is_active = true
    WHERE i.is_active = true
    ORDER BY i.slug
""")

_SQL_INSTALLATION_BY_SLUG = text("""
    SELECT i.id, i.slug, i.name
    FROM installations i
    WHERE i.slug = :slug AND i.is_active = true
    LIMIT 1
""")

_SQL_REAL_RECORDS_TS = text("""
    SELECT DISTINCT dm.derived_at_utc
    FROM derived_metrics dm
    JOIN device_installations di ON di.device_id = dm.device_id
    WHERE di.installation_id = :installation_id
      AND di.valid_to IS NULL
      AND dm.derived_at_utc >= CAST(:from_dt AS timestamptz)
      AND dm.derived_at_utc <= CAST(:to_dt AS timestamptz)
    ORDER BY dm.derived_at_utc ASC
""")

_SQL_LATEST_TS_AS_OF = text("""
    SELECT MAX(dm.derived_at_utc)
    FROM derived_metrics dm
    JOIN device_installations di ON di.device_id = dm.device_id
    WHERE di.installation_id = :installation_id
      AND di.valid_to IS NULL
      AND dm.derived_at_utc <= CAST(:as_of AS timestamptz)
""")

_SQL_SERIES_AS_OF = text("""
    SELECT dm.metric_name, dm.value, dm.derived_at_utc
    FROM derived_metrics dm
    JOIN device_installations di ON di.device_id = dm.device_id
    WHERE di.installation_id = :installation_id
      AND di.valid_to IS NULL
      AND dm.metric_name IN (
          'level_pct', 'autonomia_dias',
          'pressure', 'pressure2', 'temperature2'
      )
      AND dm.derived_at_utc >= (CAST(:as_of AS timestamptz) - INTERVAL '72 hours')
      AND dm.derived_at_utc <= CAST(:as_of AS timestamptz)
    ORDER BY dm.metric_name, dm.derived_at_utc ASC
""")

_SQL_COUNTS_AS_OF = text("""
    SELECT pm.collected_at_utc, pm.count_pulses, pm.count2_pulses
    FROM parsed_measurements pm
    WHERE pm.installation_id = :installation_id
      AND pm.collected_at_utc >= (CAST(:as_of AS timestamptz) - INTERVAL '73 hours')
      AND pm.collected_at_utc <= CAST(:as_of AS timestamptz)
    ORDER BY pm.collected_at_utc ASC
""")

_SQL_BASELINES = text("""
    SELECT metric_name, mean, std, p10, p90, sample_count, window_days, computed_at
    FROM metric_baselines
    WHERE installation_id = :installation_id
""")

# Inclui typical_variation_per_hour (diferença em relação ao backtest original)
_SQL_BEHAVIOR = text("""
    SELECT channel_role, metric_name, period_type,
           normal_low, normal_high, anomaly_low, anomaly_high,
           minimum_night_flow, profile_type, confidence,
           zero_ratio, near_zero_ratio, p50, p90, sample_count,
           typical_variation_per_hour,
           computed_at, window_start_at, window_end_at
    FROM installation_behavior_baselines
    WHERE installation_id = :installation_id
""")

# ---------------------------------------------------------------------------
# Dataclasses de resultado
# ---------------------------------------------------------------------------

@dataclass
class SimulatedAlert:
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


@dataclass
class SimulationSummary:
    total: int
    by_installation: dict[str, int] = field(default_factory=dict)
    by_rule: dict[str, int] = field(default_factory=dict)
    by_severity: dict[str, int] = field(default_factory=dict)
    shadow_count: int = 0
    active_count: int = 0


@dataclass
class SimulationResult:
    summary: SimulationSummary
    alerts: list[SimulatedAlert]
    generated_at: datetime
    evaluations_run: int
    truncated: bool
    read_only_confirmed: str


# ---------------------------------------------------------------------------
# Sessão read-only
# ---------------------------------------------------------------------------

@asynccontextmanager
async def open_readonly_session():
    """
    Sessão PostgreSQL em modo READ ONLY, com validação explícita.
    Garante ROLLBACK no finally — nunca COMMIT.
    """
    factory = _get_session_factory()
    async with factory() as session:
        try:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            ro_result = await session.execute(text("SHOW transaction_read_only"))
            ro_value = ro_result.scalar()
            if ro_value != "on":
                raise RuntimeError(
                    f"Falha ao garantir transacao read-only: "
                    f"transaction_read_only={ro_value!r} (esperado 'on'). Abortando."
                )
            yield session, ro_value
        finally:
            await session.rollback()


# ---------------------------------------------------------------------------
# Reconstrução do contexto histórico
# ---------------------------------------------------------------------------

async def build_context_as_of(
    session: AsyncSession,
    inst_id: int,
    slug: str,
    as_of: datetime,
) -> tuple[InstallationContext, bool, bool, bool]:
    """
    Reconstrói InstallationContext para o instante as_of usando dados reais do banco.
    Retorna (ctx, baseline_ready, is_stale, in_learning).
    """
    ctx = InstallationContext(
        inst_id=inst_id,
        slug=slug,
        learning_mode_until=None,
        baseline_ready_at=None,
    )

    ts_result = await session.execute(
        _SQL_LATEST_TS_AS_OF,
        {"installation_id": inst_id, "as_of": as_of},
    )
    latest_ts: datetime | None = ts_result.scalar()
    ctx.latest_ts = latest_ts

    if latest_ts is not None:
        age_s = (as_of - latest_ts).total_seconds()
        is_stale = age_s > _STALE_HOURS * 3600
    else:
        is_stale = True

    series_result = await session.execute(
        _SQL_SERIES_AS_OF,
        {"installation_id": inst_id, "as_of": as_of},
    )
    for row in series_result.fetchall():
        ctx.series.setdefault(row.metric_name, []).append(
            SeriesPoint(ts=row.derived_at_utc, value=float(row.value))
        )

    counts_result = await session.execute(
        _SQL_COUNTS_AS_OF,
        {"installation_id": inst_id, "as_of": as_of},
    )
    count_rows = counts_result.fetchall()
    if count_rows:
        lpp = float(get_settings().flow_liter_per_pulse)
        pts1 = [(ts, c1) for ts, c1, _c2 in count_rows]
        pts2 = [(ts, c2) for ts, _c1, c2 in count_rows]
        flow1 = windowed_flow_series(pts1, liter_per_pulse=lpp)
        flow2 = windowed_flow_series(pts2, liter_per_pulse=lpp)
        for ts, v in flow1:
            ctx.series.setdefault("flow1_lph", []).append(SeriesPoint(ts=ts, value=v))
        for ts, v in flow2:
            ctx.series.setdefault("flow2_lph", []).append(SeriesPoint(ts=ts, value=v))
        for (ts, v1), (_, v2) in zip(flow1, flow2, strict=True):
            ctx.series.setdefault("flow_total_lph", []).append(
                SeriesPoint(ts=ts, value=v1 + v2)
            )

    bl_result = await session.execute(_SQL_BASELINES, {"installation_id": inst_id})
    for row in bl_result.fetchall():
        ctx.baselines[row.metric_name] = {
            "mean":         float(row.mean or 0),
            "std":          float(row.std  or 0),
            "p10":          float(row.p10  or 0) if row.p10  is not None else 0.0,
            "p90":          float(row.p90  or 0) if row.p90  is not None else 0.0,
            "sample_count": float(row.sample_count or 0),
            "window_days":  float(row.window_days  or 0),
        }

    beh_result = await session.execute(_SQL_BEHAVIOR, {"installation_id": inst_id})
    beh_rows = beh_result.fetchall()
    computed_times: list[datetime] = []
    for row in beh_rows:
        key = (row.channel_role, row.metric_name, row.period_type)
        ctx.behavior[key] = {
            "normal_low":                 row.normal_low,
            "normal_high":                row.normal_high,
            "anomaly_low":                row.anomaly_low,
            "anomaly_high":               row.anomaly_high,
            "minimum_night_flow":         row.minimum_night_flow,
            "profile_type":               row.profile_type,
            "confidence":                 row.confidence,
            "zero_ratio":                 row.zero_ratio,
            "near_zero_ratio":            row.near_zero_ratio,
            "p50":                        row.p50,
            "p90":                        row.p90,
            "sample_count":               row.sample_count,
            "typical_variation_per_hour": row.typical_variation_per_hour,
        }
        if row.computed_at is not None:
            computed_times.append(row.computed_at)
    if computed_times:
        ctx.behavior_last_computed = max(computed_times)

    ctx.capabilities = await get_installation_capabilities(inst_id, session, slug=slug)

    baseline_ready = bool(ctx.baselines)
    in_learning = False

    return ctx, baseline_ready, is_stale, in_learning


def simulate_point(
    ctx: InstallationContext,
    as_of: datetime,
    baseline_ready: bool,
    is_stale: bool,
    in_learning: bool,
) -> list[DetectorResult]:
    """Chama _run_pipeline em memória (função pura — sem acesso ao DB)."""
    return _run_pipeline(
        ctx,
        now=as_of,
        baseline_ready=baseline_ready,
        is_stale=is_stale,
        in_learning=in_learning,
    )


# ---------------------------------------------------------------------------
# Dedupe
# ---------------------------------------------------------------------------

def _dedupe(
    alerts: list[SimulatedAlert],
    window_minutes: int,
) -> list[SimulatedAlert]:
    """
    Colapsa repetições de (installation_slug, rule_key) dentro de window_minutes,
    mantendo o mais recente e somando occurrences.
    """
    if window_minutes <= 0:
        return alerts

    window_s = window_minutes * 60
    # Ordenar por timestamp asc para processar em ordem cronológica
    ordered = sorted(alerts, key=lambda a: a.timestamp)
    buckets: dict[tuple[str, str], SimulatedAlert] = {}

    result: list[SimulatedAlert] = []
    for alert in ordered:
        key = (alert.installation_slug, alert.rule_key)
        if key in buckets:
            existing = buckets[key]
            delta = (alert.timestamp - existing.timestamp).total_seconds()
            if delta <= window_s:
                # Atualiza para a ocorrência mais recente e incrementa contagem.
                # Todos os campos descritivos precisam ser substituídos para evitar
                # cartão contraditório (ex.: mensagem falando em 17.0 p.p. mas
                # observed_value mostrando 22.0).
                saved_occurrences = existing.occurrences + alert.occurrences
                saved_shadow = existing.shadow
                # Substitui o bucket pelo alerta mais recente
                existing.timestamp        = alert.timestamp
                existing.severity         = alert.severity
                existing.current_value    = alert.current_value
                existing.observed_value   = alert.observed_value
                existing.normal_high      = alert.normal_high
                existing.anomaly_high     = alert.anomaly_high
                existing.reason           = alert.reason
                existing.severity_reason  = alert.severity_reason
                existing.mensagem_usuario = alert.mensagem_usuario
                existing.recomendacao     = alert.recomendacao
                existing.dados_relevantes = alert.dados_relevantes
                existing.metric_used      = alert.metric_used
                existing.shadow           = saved_shadow  # shadow permanece do bucket original
                existing.occurrences      = saved_occurrences
                continue
            else:
                result.append(existing)
        buckets[key] = SimulatedAlert(
            timestamp=alert.timestamp,
            installation_slug=alert.installation_slug,
            installation_name=alert.installation_name,
            rule_key=alert.rule_key,
            severity=alert.severity,
            shadow=alert.shadow,
            metric_used=alert.metric_used,
            current_value=alert.current_value,
            observed_value=alert.observed_value,
            normal_high=alert.normal_high,
            anomaly_high=alert.anomaly_high,
            reason=alert.reason,
            severity_reason=alert.severity_reason,
            mensagem_usuario=alert.mensagem_usuario,
            recomendacao=alert.recomendacao,
            dados_relevantes=alert.dados_relevantes,
            occurrences=1,
        )

    result.extend(buckets.values())
    return result


# ---------------------------------------------------------------------------
# run_simulation — ponto de entrada público
# ---------------------------------------------------------------------------

async def run_simulation(
    *,
    from_dt: datetime,
    to_dt: datetime,
    installation_slug: str | None,
    mode: Literal["real_records", "fixed_step"],
    limit: int,
    step_minutes: int,
    include_shadow: bool,
    dedupe_window_minutes: int,
) -> SimulationResult:
    """
    Varre o período [from_dt, to_dt] e retorna os alertas que o motor atual geraria.
    100% read-only: não chama _apply_result, não escreve no banco.
    """

    async def _inner() -> SimulationResult:
        raw_alerts: list[SimulatedAlert] = []
        evaluations = 0
        truncated = False
        ro_confirmed = "unknown"

        async with open_readonly_session() as (session, ro_value):
            ro_confirmed = ro_value

            # Resolver instalações
            if installation_slug:
                r = await session.execute(
                    _SQL_INSTALLATION_BY_SLUG, {"slug": installation_slug}
                )
                row = r.fetchone()
                if not row:
                    raise ValueError(f"Instalação não encontrada ou inativa: {installation_slug!r}")
                installations = [(row.id, row.slug, row.name)]
            else:
                r = await session.execute(_SQL_ACTIVE_INSTALLATIONS)
                installations = [(row.id, row.slug, row.name) for row in r.fetchall()]

            if not installations:
                raise ValueError("Nenhuma instalação ativa encontrada.")

            for inst_id, slug, inst_name in installations:
                # Gerar pontos as_of
                if mode == "real_records":
                    ts_result = await session.execute(
                        _SQL_REAL_RECORDS_TS,
                        {"installation_id": inst_id, "from_dt": from_dt, "to_dt": to_dt},
                    )
                    as_of_points = [row.derived_at_utc for row in ts_result.fetchall()]
                else:
                    # fixed_step
                    as_of_points = []
                    current = from_dt
                    step_s = step_minutes * 60
                    while current <= to_dt:
                        as_of_points.append(current)
                        current = datetime.fromtimestamp(
                            current.timestamp() + step_s, tz=UTC
                        )

                for as_of in as_of_points:
                    if evaluations >= _MAX_EVALUATIONS:
                        truncated = True
                        logger.warning(
                            "alert_simulation.max_evaluations_reached",
                            evaluations=evaluations,
                            installation=slug,
                        )
                        break

                    sp_name = f"sp_sim_{inst_id}_{evaluations}"
                    try:
                        await session.execute(text(f"SAVEPOINT {sp_name}"))
                        ctx, baseline_ready, is_stale, in_learning = await build_context_as_of(
                            session, inst_id, slug, as_of
                        )
                        await session.execute(text(f"RELEASE SAVEPOINT {sp_name}"))
                    except Exception as exc:
                        logger.warning(
                            "alert_simulation.context_error",
                            installation=slug,
                            as_of=as_of.isoformat(),
                            error=str(exc),
                        )
                        try:
                            await session.execute(text(f"ROLLBACK TO SAVEPOINT {sp_name}"))
                            await session.execute(text(f"RELEASE SAVEPOINT {sp_name}"))
                        except Exception:
                            pass
                        evaluations += 1
                        continue

                    detector_results = simulate_point(ctx, as_of, baseline_ready, is_stale, in_learning)
                    evaluations += 1

                    for det in detector_results:
                        if not det.is_active:
                            continue
                        is_shadow = det.rule_key in _SHADOW_ONLY_RULES
                        if is_shadow and not include_shadow:
                            continue
                        dr = det.dados_relevantes or {}
                        raw_alerts.append(SimulatedAlert(
                            timestamp=as_of,
                            installation_slug=slug,
                            installation_name=inst_name,
                            rule_key=det.rule_key,
                            severity=det.severity,
                            shadow=is_shadow,
                            metric_used=dr.get("metric_used"),
                            current_value=det.current_value,
                            observed_value=dr.get("observed_value"),
                            normal_high=dr.get("normal_high"),
                            anomaly_high=dr.get("anomaly_high"),
                            reason=det.reason,
                            severity_reason=dr.get("severity_reason"),
                            mensagem_usuario=det.mensagem_usuario,
                            recomendacao=det.recomendacao,
                            dados_relevantes=dr,
                        ))

                if truncated:
                    break

        # Dedupe
        deduped = _dedupe(raw_alerts, dedupe_window_minutes)

        # Ordenar desc por timestamp
        deduped.sort(key=lambda a: a.timestamp, reverse=True)

        # Cap de saída
        if len(deduped) > limit:
            deduped = deduped[:limit]
            truncated = True

        # Montar summary
        by_installation: dict[str, int] = {}
        by_rule: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        shadow_count = 0
        active_count = 0

        for a in deduped:
            by_installation[a.installation_slug] = by_installation.get(a.installation_slug, 0) + a.occurrences
            by_rule[a.rule_key] = by_rule.get(a.rule_key, 0) + a.occurrences
            sev = a.severity or "desconhecida"
            by_severity[sev] = by_severity.get(sev, 0) + a.occurrences
            if a.shadow:
                shadow_count += a.occurrences
            else:
                active_count += a.occurrences

        total = sum(a.occurrences for a in deduped)
        summary = SimulationSummary(
            total=total,
            by_installation=by_installation,
            by_rule=by_rule,
            by_severity=by_severity,
            shadow_count=shadow_count,
            active_count=active_count,
        )

        return SimulationResult(
            summary=summary,
            alerts=deduped,
            generated_at=datetime.now(UTC),
            evaluations_run=evaluations,
            truncated=truncated,
            read_only_confirmed=ro_confirmed,
        )

    try:
        return await asyncio.wait_for(_inner(), timeout=_SIMULATION_TIMEOUT_S)
    except TimeoutError as exc:
        logger.warning("alert_simulation.timeout", timeout_s=_SIMULATION_TIMEOUT_S)
        raise TimeoutError(
            f"Simulação excedeu o tempo limite de {_SIMULATION_TIMEOUT_S}s. "
            "Reduza o intervalo ou use um passo maior."
        ) from exc
