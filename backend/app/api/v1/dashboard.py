"""
/api/v1/installations/{slug}/dashboard — Snapshot real por device (analógico DTN-200-FPS0).
/api/v1/installations/{slug}/topology  — Estado por device (per-device metrics + alertas).

Somente dados reais: level_pct, level_m, current_ma, battery_v, signal, voltage_v.
Sem pressão/vazão/consumo — hardware analógico não os produz.

level_pct / percentual retornados são NOMINAIS (base altura_util 1,648 m), não escala do sensor.
sensor_level_pct = campo técnico (% escala 0–4 m), não usado como headline.

Acesso protegido: requer usuário autenticado (approved). Usuários pending/rejected/inactive são
bloqueados pelo JWT — o token só é emitido para status=approved.
"""
from __future__ import annotations

import zoneinfo
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbDep
from app.processing.derivations import flow_from_level
from app.processing.derivations import reservoir as res_calc
from app.services import reservoir_config

router = APIRouter(tags=["dashboard"])

_LATEST_METRICS = ("level_pct", "level_m", "current_ma", "battery_v", "signal", "voltage_v")
_SERIES_METRICS = ("level_pct", "level_m", "current_ma", "battery_v", "signal", "voltage_v")
_ACTIVE_WINDOW_MIN = 60
_FULL_ESTIMATE_TZ = "America/Sao_Paulo"


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_SQL_DEVICES = text("""
    SELECT
        d.id     AS device_id,
        d.imei,
        d.label,
        d.model,
        d.status AS device_status,
        (
            SELECT MAX(pm.collected_at_utc)
            FROM parsed_measurements pm
            WHERE pm.device_id = d.id
        ) AS last_seen_utc
    FROM devices d
    JOIN device_installations di ON di.device_id = d.id AND di.valid_to IS NULL
    WHERE di.installation_id = :installation_id
      AND d.is_active = true
    ORDER BY d.id
""")

_SQL_LATEST = text("""
    SELECT DISTINCT ON (dm.device_id, dm.metric_name)
        dm.device_id,
        dm.metric_name,
        dm.value,
        dm.derived_at_utc
    FROM derived_metrics dm
    WHERE dm.device_id = ANY(:device_ids)
      AND dm.metric_name = ANY(:metrics)
    ORDER BY dm.device_id, dm.metric_name, dm.derived_at_utc DESC
""")

_SQL_SERIES = text("""
    SELECT
        dm.device_id,
        dm.metric_name,
        dm.value,
        dm.derived_at_utc
    FROM derived_metrics dm
    WHERE dm.device_id = ANY(:device_ids)
      AND dm.metric_name = ANY(:metrics)
      AND dm.derived_at_utc >= :from_dt AND dm.derived_at_utc < :to_dt
    ORDER BY dm.device_id, dm.metric_name, dm.derived_at_utc ASC
""")

_SQL_TOPOLOGY = text("""
    SELECT
        d.id        AS device_id,
        d.imei,
        d.label,
        d.model,
        d.status    AS device_status,
        (
            SELECT MAX(pm.collected_at_utc)
            FROM parsed_measurements pm
            WHERE pm.device_id = d.id
        ) AS last_seen_utc,
        (
            SELECT json_object_agg(sq.metric_name, sq.value)
            FROM (
                SELECT DISTINCT ON (dm2.metric_name)
                    dm2.metric_name, dm2.value
                FROM derived_metrics dm2
                WHERE dm2.device_id = d.id
                ORDER BY dm2.metric_name, dm2.derived_at_utc DESC
            ) sq
        ) AS latest_metrics,
        (
            SELECT json_agg(json_build_object(
                'rule_key', als.rule_key,
                'severity', als.severity,
                'titulo',   als.titulo
            ))
            FROM alert_state als
            WHERE als.device_id = d.id
              AND als.is_active = true
        ) AS active_alerts
    FROM devices d
    JOIN device_installations di ON di.device_id = d.id AND di.valid_to IS NULL
    JOIN installations i ON i.id = di.installation_id
    WHERE i.slug = :slug
      AND d.is_active = true
    ORDER BY d.id
""")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class DashSeriesPoint(BaseModel):
    t: int
    v: float


class DashDeviceLatest(BaseModel):
    # Escala nominal (headline)
    level_pct: Optional[float] = None       # alias de percentual (compat)
    level_m: Optional[float] = None
    current_ma: Optional[float] = None
    battery_v: Optional[float] = None
    signal: Optional[float] = None
    voltage_v: Optional[float] = None
    # Campos explícitos nominais
    nivel_m: Optional[float] = None
    percentual: Optional[float] = None
    volume_tank_l: Optional[float] = None
    volume_group_l: Optional[float] = None
    faltante_tank_l: Optional[float] = None
    faltante_group_l: Optional[float] = None
    altura_faltante_m: Optional[float] = None
    # Compat
    volume_l: Optional[float] = None       # = volume_group_l
    faltante_l: Optional[float] = None     # = faltante_group_l
    # Campo técnico (escala bruta do sensor 0–4 m, diagnóstico)
    sensor_level_pct: Optional[float] = None


class DashDevice(BaseModel):
    device_id: int
    imei: str
    label: Optional[str]
    model: Optional[str]
    status: Optional[str]
    last_seen_utc: Optional[str]
    active: bool
    latest: DashDeviceLatest
    series: dict[str, list[DashSeriesPoint]]
    group_name: Optional[str] = None
    group_capacity_l: Optional[float] = None
    tank_count: Optional[int] = None


class InstallationDashboardResponse(BaseModel):
    installation_slug: str
    installation_name: str
    hours: int
    last_seen_utc: Optional[str]
    device_count: int
    active_count: int
    devices: list[DashDevice]
    volume_total_l: float = 0.0
    faltante_total_l: float = 0.0
    capacidade_total_l: float = 0.0
    consumption_summary: Optional[ConsumptionSummary] = None


class DeviceTopology(BaseModel):
    device_id: int
    imei: str
    label: Optional[str]
    model: Optional[str]
    device_status: Optional[str]
    last_seen_utc: Optional[str]
    current_ma: Optional[float] = None
    level_m: Optional[float] = None
    level_pct: Optional[float] = None
    voltage_v: Optional[float] = None
    battery_v: Optional[float] = None
    signal: Optional[float] = None
    sensor_fault: Optional[bool] = None
    active_alerts: list[dict[str, Any]] = []
    pressure: None = None
    flow: None = None


class TopologyResponse(BaseModel):
    installation_slug: str
    installation_name: str
    devices: list[DeviceTopology]


class ShiftWindow(BaseModel):
    label: str
    start: str
    end: str


class ConsumptionSummary(BaseModel):
    total_m3: float
    period_1_m3: float
    period_2_m3: float
    period_1: ShiftWindow
    period_2: ShiftWindow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_hhmm(s: str, default_min: int) -> int:
    """Parse 'HH:MM' → minutes-of-day. Returns default_min on invalid input."""
    try:
        parts = s.strip().split(":")
        if len(parts) != 2:
            return default_min
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return default_min
        return h * 60 + m
    except (ValueError, AttributeError):
        return default_min


def _fmt_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _ts_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch_ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


async def _find_installation(db, slug: str):
    from types import SimpleNamespace

    raw = (slug or "").strip()
    candidates = []

    if raw:
        candidates.append(raw)
        candidates.append(raw.replace("-", "_"))

    candidates.append("hospital_santa_ana")

    seen = set()

    for candidate in candidates:
        if not candidate or candidate in seen:
            continue

        seen.add(candidate)

        result = await db.execute(
            text("""
                SELECT
                    id, slug, name, lat, lng,
                    group_name, is_active, notes, created_at, updated_at
                FROM installations
                WHERE slug = :slug
                LIMIT 1
            """),
            {"slug": candidate},
        )

        row = result.mappings().first()

        if row:
            return SimpleNamespace(**dict(row))

    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/installations/{slug}/dashboard", response_model=InstallationDashboardResponse)
async def get_dashboard(
    slug: str,
    db: DbDep,
    _user: CurrentUser,
    hours: int = Query(24, ge=1, le=720),
    shift_start: str = Query("07:00"),
    shift_end: str = Query("19:00"),
    start_date: str | None = Query(None, description="YYYY-MM-DD (America/Sao_Paulo)"),
    end_date: str | None = Query(None, description="YYYY-MM-DD (America/Sao_Paulo)"),
):
    """Snapshot real por device + série temporal nas últimas `hours` horas."""
    inst = await _find_installation(db, slug)
    if not inst:
        raise HTTPException(status_code=404, detail="Instalação não encontrada")

    _tz_window = zoneinfo.ZoneInfo(_FULL_ESTIMATE_TZ)
    if start_date and end_date:
        try:
            from_dt = datetime.fromisoformat(start_date).replace(tzinfo=_tz_window)
            to_dt = datetime.fromisoformat(end_date).replace(tzinfo=_tz_window) + timedelta(days=1)
        except ValueError:
            raise HTTPException(status_code=422, detail="Datas inválidas (use YYYY-MM-DD)")
        if from_dt >= to_dt or (to_dt - from_dt) > timedelta(days=31):
            raise HTTPException(status_code=422, detail="Intervalo inválido (1 a 31 dias, início ≤ fim)")
    else:
        to_dt = datetime.now(tz=timezone.utc)
        from_dt = to_dt - timedelta(hours=hours)

    device_rows = (await db.execute(_SQL_DEVICES, {"installation_id": inst.id})).fetchall()

    if not device_rows:
        return InstallationDashboardResponse(
            installation_slug=inst.slug,
            installation_name=inst.name,
            hours=hours,
            last_seen_utc=None,
            device_count=0,
            active_count=0,
            devices=[],
        )

    device_ids = [r.device_id for r in device_rows]

    # Última leitura por (device, metric)
    latest_rows = (await db.execute(
        _SQL_LATEST,
        {"device_ids": device_ids, "metrics": list(_LATEST_METRICS)},
    )).fetchall()
    latest_by_device: dict[int, dict[str, float]] = {}
    for device_id, metric_name, value, _ts in latest_rows:
        latest_by_device.setdefault(device_id, {})[metric_name] = value

    # Série temporal por (device, metric)
    series_rows = (await db.execute(
        _SQL_SERIES,
        {"device_ids": device_ids, "metrics": list(_SERIES_METRICS), "from_dt": from_dt, "to_dt": to_dt},
    )).fetchall()
    series_by_device: dict[int, dict[str, list[DashSeriesPoint]]] = {}
    for device_id, metric_name, value, ts in series_rows:
        bucket = series_by_device.setdefault(device_id, {})
        bucket.setdefault(metric_name, []).append(
            DashSeriesPoint(t=_epoch_ms(ts), v=float(value))
        )

    # Config de reservatório por grupo (resiliente — fallback se tabela não existir)
    groups = await reservoir_config.load_groups(db, inst.id)

    now = datetime.now(timezone.utc)
    devices: list[DashDevice] = []
    overall_last_seen: Optional[datetime] = None
    active_count = 0

    # Acumuladores para totais por grupo distinto (sem dupla contagem)
    # group_key → {"cfg": ReservoirConfig, "tank_pcts": list[float]}
    group_aggregates: dict[str, dict] = {}

    # Consumo acumulado por turno (m³)
    shift_start_min = _parse_hhmm(shift_start, 7 * 60)
    shift_end_min = _parse_hhmm(shift_end, 19 * 60)
    _tz = zoneinfo.ZoneInfo(_FULL_ESTIMATE_TZ)
    cons_p1_l = 0.0
    cons_p2_l = 0.0

    for i, r in enumerate(device_rows):
        last_seen: Optional[datetime] = r.last_seen_utc
        is_active = (
            last_seen is not None
            and (now - (last_seen if last_seen.tzinfo else last_seen.replace(tzinfo=timezone.utc))).total_seconds()
            <= _ACTIVE_WINDOW_MIN * 60
        )
        if is_active:
            active_count += 1
        if last_seen is not None and (overall_last_seen is None or last_seen > overall_last_seen):
            overall_last_seen = last_seen

        lm = latest_by_device.get(r.device_id, {})
        dev_series = series_by_device.get(r.device_id, {})

        # Resolver config do grupo para este device (por índice de posição; post-migration: por FK)
        cfg = reservoir_config.resolve_device_cfg(None, groups, i)

        # Campo técnico: % bruta da escala do sensor (0–4 m), gravada em derived_metrics
        sensor_level_pct_latest = lm.get("level_pct")

        # Cálculo nominal a partir de level_m
        level_m_latest = lm.get("level_m")
        ro = res_calc.readout(level_m_latest, cfg) if level_m_latest is not None else None

        # level_pct do dashboard = percentual nominal (substitui p90)
        percentual_latest = ro["percentual"] if ro else None
        level_pct_latest = percentual_latest

        # Série level_pct nominal derivada de level_m
        level_m_series = dev_series.get("level_m", [])
        if level_m_series:
            level_pct_series = [
                DashSeriesPoint(t=p.t, v=res_calc.tank_percent(p.v, cfg))
                for p in level_m_series
            ]
        else:
            level_pct_series = dev_series.get("level_pct", [])

        series_out = {m: dev_series.get(m, []) for m in _SERIES_METRICS}
        series_out["level_pct"] = level_pct_series

        # Vazão derivada de nível nominal — L/h reais do grupo
        if level_pct_series:
            _pts = [(p.t, p.v) for p in level_pct_series]
            series_out["flow_consumo_lph"] = [
                DashSeriesPoint(t=t, v=v)
                for t, v in flow_from_level.consumption_series(_pts, cfg.group_capacity_l)
            ]
            hourly_buckets = list(flow_from_level.net_flow_hourly(_pts, cfg.group_capacity_l, _FULL_ESTIMATE_TZ))
            series_out["flow_hourly_lph"] = [
                DashSeriesPoint(t=t, v=v) for t, v in hourly_buckets
            ]
            # Accumulate consumption for shift breakdown (queda retificada por turno)
            for bucket_end_ms, delta_l in hourly_buckets:
                consumed = max(0.0, -delta_l)
                if consumed <= 0.0:
                    continue
                bucket_start_ms = bucket_end_ms - 3_600_000
                local_dt = datetime.fromtimestamp(bucket_start_ms / 1000, tz=_tz)
                minute_of_day = local_dt.hour * 60 + local_dt.minute
                if shift_start_min < shift_end_min:
                    in_p1 = shift_start_min <= minute_of_day < shift_end_min
                else:
                    in_p1 = minute_of_day >= shift_start_min or minute_of_day < shift_end_min
                if in_p1:
                    cons_p1_l += consumed
                else:
                    cons_p2_l += consumed

        # Acumulação para totais por grupo distinto
        # Antes da migration: cada device = grupo único por índice
        group_key = f"idx_{i}"
        if group_key not in group_aggregates:
            group_aggregates[group_key] = {"cfg": cfg, "tank_pcts": []}
        if ro is not None:
            group_aggregates[group_key]["tank_pcts"].append(ro["percentual"])

        # group_name do grupo resolvido (se disponível)
        resolved_group_name: Optional[str] = None
        if i < len(groups):
            resolved_group_name = groups[i].get("group_name")

        devices.append(DashDevice(
            device_id=r.device_id,
            imei=r.imei,
            label=r.label,
            model=r.model,
            status=r.device_status,
            last_seen_utc=_ts_z(last_seen) if last_seen else None,
            active=is_active,
            latest=DashDeviceLatest(
                level_pct=level_pct_latest,
                level_m=level_m_latest,
                current_ma=lm.get("current_ma"),
                battery_v=lm.get("battery_v"),
                signal=lm.get("signal"),
                voltage_v=lm.get("voltage_v"),
                nivel_m=ro["nivel_m"] if ro else None,
                percentual=percentual_latest,
                volume_tank_l=ro["volume_tank_l"] if ro else None,
                volume_group_l=ro["volume_group_l"] if ro else None,
                faltante_tank_l=ro["faltante_tank_l"] if ro else None,
                faltante_group_l=ro["faltante_group_l"] if ro else None,
                altura_faltante_m=ro["altura_faltante_m"] if ro else None,
                volume_l=ro["volume_group_l"] if ro else None,
                faltante_l=ro["faltante_group_l"] if ro else None,
                sensor_level_pct=sensor_level_pct_latest,
            ),
            series=series_out,
            group_name=resolved_group_name,
            group_capacity_l=cfg.group_capacity_l,
            tank_count=cfg.tank_count,
        ))

    # Totais por grupo distinto (sem dupla contagem)
    volume_total_l = 0.0
    faltante_total_l = 0.0
    capacidade_total_l = 0.0
    for gagg in group_aggregates.values():
        cfg_g = gagg["cfg"]
        tank_pcts = gagg["tank_pcts"]
        if not tank_pcts:
            continue
        # Caixas equalizadas: média dos tank_percent dos sensores do grupo
        avg_pct = sum(tank_pcts) / len(tank_pcts)
        g_vol = max(0.0, min(cfg_g.group_capacity_l, avg_pct / 100.0 * cfg_g.group_capacity_l))
        volume_total_l += g_vol
        faltante_total_l += cfg_g.group_capacity_l - g_vol
        capacidade_total_l += cfg_g.group_capacity_l

    consumption_summary = ConsumptionSummary(
        total_m3=round((cons_p1_l + cons_p2_l) / 1000, 2),
        period_1_m3=round(cons_p1_l / 1000, 2),
        period_2_m3=round(cons_p2_l / 1000, 2),
        period_1=ShiftWindow(
            label=f"{shift_start}–{shift_end}",
            start=shift_start,
            end=shift_end,
        ),
        period_2=ShiftWindow(
            label=f"{shift_end}–{shift_start}",
            start=shift_end,
            end=shift_start,
        ),
    )

    return InstallationDashboardResponse(
        installation_slug=inst.slug,
        installation_name=inst.name,
        hours=hours,
        last_seen_utc=_ts_z(overall_last_seen) if overall_last_seen else None,
        device_count=len(devices),
        active_count=active_count,
        devices=devices,
        volume_total_l=round(volume_total_l, 1),
        faltante_total_l=round(faltante_total_l, 1),
        capacidade_total_l=round(capacidade_total_l, 1),
        consumption_summary=consumption_summary,
    )


@router.get("/installations/{slug}/topology", response_model=TopologyResponse)
async def get_topology(slug: str, db: DbDep, _user: CurrentUser):
    """Estado por device analógico registrado na instalação."""
    inst = await _find_installation(db, slug)
    if not inst:
        raise HTTPException(status_code=404, detail="Instalação não encontrada")

    topo_result = await db.execute(_SQL_TOPOLOGY, {"slug": inst.slug})
    rows = topo_result.fetchall()

    devices: list[DeviceTopology] = []
    for row in rows:
        metrics: dict = row.latest_metrics or {}
        alerts: list = row.active_alerts or []

        has_sensor_fault = any(a.get("rule_key") == "sensor_fault" for a in alerts)

        devices.append(DeviceTopology(
            device_id=row.device_id,
            imei=row.imei,
            label=row.label,
            model=row.model,
            device_status=row.device_status,
            last_seen_utc=_ts_z(row.last_seen_utc) if row.last_seen_utc else None,
            current_ma=metrics.get("current_ma"),
            level_m=metrics.get("level_m"),
            level_pct=metrics.get("level_pct"),
            voltage_v=metrics.get("voltage_v"),
            battery_v=metrics.get("battery_v"),
            signal=metrics.get("signal"),
            sensor_fault=has_sensor_fault or None,
            active_alerts=alerts,
        ))

    return TopologyResponse(
        installation_slug=inst.slug,
        installation_name=inst.name,
        devices=devices,
    )
