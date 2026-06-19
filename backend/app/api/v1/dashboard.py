"""
/api/v1/installations/{slug}/dashboard — Snapshot real por device (analógico DTN-200-FPS0).
/api/v1/installations/{slug}/topology  — Estado por device (per-device metrics + alertas).

Somente dados reais: level_pct, level_m, current_ma, battery_v, signal, voltage_v.
Sem pressão/vazão/consumo — hardware analógico não os produz.

Acesso público (sem auth), como /health: o frontend do hospital usa login mock
(sem JWT real). Reavaliar quando houver autenticação real ponta a ponta.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbDep
from app.db.models.installation import Installation

router = APIRouter(tags=["dashboard"])

# Métricas reais disponíveis para o hospital (analógico)
_LATEST_METRICS = ("level_pct", "level_m", "current_ma", "battery_v", "signal", "voltage_v")
_SERIES_METRICS = ("level_pct", "level_m", "current_ma", "battery_v", "signal", "voltage_v")
# Device considerado "ativo" se reportou nos últimos N minutos
_ACTIVE_WINDOW_MIN = 60


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

# Devices vinculados à instalação (vínculo ativo) + última coleta
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

# Última leitura por (device, metric) — DISTINCT ON evita colapsar devices/grupos
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

# Série temporal por device nas últimas N horas
_SQL_SERIES = text("""
    SELECT
        dm.device_id,
        dm.metric_name,
        dm.value,
        dm.derived_at_utc
    FROM derived_metrics dm
    WHERE dm.device_id = ANY(:device_ids)
      AND dm.metric_name = ANY(:metrics)
      AND dm.derived_at_utc >= now() - :hours * INTERVAL '1 hour'
    ORDER BY dm.device_id, dm.metric_name, dm.derived_at_utc ASC
""")

# Pico de level_m por device nos últimos 30 dias = referência de 100% de enchimento.
# Janela fixa (independente do parâmetro `hours` da rota). Usa level_m (não current_ma)
# porque level_m só é gravado quando a corrente está na faixa válida → exclui spikes de
# undercurrent/overrange automaticamente.
_SQL_PEAK_LEVEL_30D = text("""
    SELECT dm.device_id, MAX(dm.value) AS peak_level_m
    FROM derived_metrics dm
    WHERE dm.device_id = ANY(:device_ids)
      AND dm.metric_name = 'level_m'
      AND dm.value IS NOT NULL
      AND dm.derived_at_utc >= now() - INTERVAL '30 days'
    GROUP BY dm.device_id
""")

# Topology: estado por device registrado na instalação (mantido)
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
    t: int          # epoch ms (UTC)
    v: float


class DashDeviceLatest(BaseModel):
    level_pct: Optional[float] = None
    level_m: Optional[float] = None
    current_ma: Optional[float] = None
    battery_v: Optional[float] = None
    signal: Optional[float] = None
    voltage_v: Optional[float] = None


class DashDevice(BaseModel):
    device_id: int
    imei: str
    label: Optional[str]
    model: Optional[str]
    status: Optional[str]
    last_seen_utc: Optional[str]
    active: bool
    latest: DashDeviceLatest
    # séries por métrica: level_pct, level_m, current_ma
    series: dict[str, list[DashSeriesPoint]]


class InstallationDashboardResponse(BaseModel):
    installation_slug: str
    installation_name: str
    hours: int
    last_seen_utc: Optional[str]
    device_count: int
    active_count: int
    devices: list[DashDevice]


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch_ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _fill_pct(level_m: Optional[float], peak_level_m: Optional[float]) -> Optional[float]:
    """% de enchimento relativa ao pico de nível dos últimos 30 dias (100% = pico).

    Retorna None quando não há leitura de nível ou pico válido — o chamador faz
    fallback para o level_pct armazenado (escala do sensor).
    """
    if level_m is None or peak_level_m is None or peak_level_m <= 0:
        return None
    return max(0.0, min(100.0, level_m / peak_level_m * 100.0))


async def _find_installation(db, slug: str):
    """Busca instalação usando apenas colunas existentes no schema atual."""
    from types import SimpleNamespace
    from sqlalchemy import text

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
                    id,
                    slug,
                    name,
                    lat,
                    lng,
                    group_name,
                    is_active,
                    notes,
                    created_at,
                    updated_at
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


@router.get("/installations/{slug}/dashboard", response_model=InstallationDashboardResponse)
async def get_dashboard(
    slug: str,
    db: DbDep,
    hours: int = Query(24, ge=1, le=720),
):
    """Snapshot real por device + série temporal nas últimas `hours` horas."""
    inst = await _find_installation(db, slug)
    if not inst:
        raise HTTPException(status_code=404, detail="Instalação não encontrada")

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
        {"device_ids": device_ids, "metrics": list(_SERIES_METRICS), "hours": hours},
    )).fetchall()
    series_by_device: dict[int, dict[str, list[DashSeriesPoint]]] = {}
    for device_id, metric_name, value, ts in series_rows:
        bucket = series_by_device.setdefault(device_id, {})
        bucket.setdefault(metric_name, []).append(
            DashSeriesPoint(t=_epoch_ms(ts), v=float(value))
        )

    # Pico de level_m por device (30 d) — referência de 100% de enchimento.
    peak_rows = (await db.execute(
        _SQL_PEAK_LEVEL_30D,
        {"device_ids": device_ids},
    )).fetchall()
    peak_by_device: dict[int, float] = {
        device_id: float(peak)
        for device_id, peak in peak_rows
        if peak is not None
    }

    now = datetime.now(timezone.utc)
    devices: list[DashDevice] = []
    overall_last_seen: Optional[datetime] = None
    active_count = 0

    for r in device_rows:
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
        peak = peak_by_device.get(r.device_id)

        # level_pct passa a ser % de enchimento vs pico de 30 d (100% = pico).
        # Fallback ao level_pct armazenado (escala do sensor) quando não há pico.
        fill_latest = _fill_pct(lm.get("level_m"), peak)
        level_pct_latest = fill_latest if fill_latest is not None else lm.get("level_pct")

        level_m_series = dev_series.get("level_m", [])
        if peak and peak > 0 and level_m_series:
            level_pct_series = [
                DashSeriesPoint(t=p.t, v=max(0.0, min(100.0, p.v / peak * 100.0)))
                for p in level_m_series
            ]
        else:
            level_pct_series = dev_series.get("level_pct", [])

        series_out = {m: dev_series.get(m, []) for m in _SERIES_METRICS}
        series_out["level_pct"] = level_pct_series

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
                level_m=lm.get("level_m"),
                current_ma=lm.get("current_ma"),
                battery_v=lm.get("battery_v"),
                signal=lm.get("signal"),
                voltage_v=lm.get("voltage_v"),
            ),
            series=series_out,
        ))

    return InstallationDashboardResponse(
        installation_slug=inst.slug,
        installation_name=inst.name,
        hours=hours,
        last_seen_utc=_ts_z(overall_last_seen) if overall_last_seen else None,
        device_count=len(devices),
        active_count=active_count,
        devices=devices,
    )


@router.get("/installations/{slug}/topology", response_model=TopologyResponse)
async def get_topology(slug: str, db: DbDep):
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
