"""
/api/v1/installations/{slug}/dashboard — Snapshot das métricas mais recentes.
/api/v1/installations/{slug}/topology  — Estado por device (per-device metrics + alertas).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text

from app.api.deps import CurrentUser, DbDep
from app.db.models.installation import Installation
from app.schemas.telemetry import DashboardResponse, MetricSnapshot

router = APIRouter(tags=["dashboard"])


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

# DISTINCT ON (device_id, metric_name) — evita misturar leituras de grupos
_SQL_LATEST = text("""
    SELECT DISTINCT ON (dm.device_id, dm.metric_name)
        dm.device_id,
        dm.metric_name,
        dm.value,
        dm.unit,
        dm.derived_at_utc
    FROM derived_metrics dm
    JOIN device_installations di ON di.device_id = dm.device_id
    JOIN installations i ON i.id = di.installation_id
    WHERE i.slug = :slug
      AND di.valid_to IS NULL
    ORDER BY dm.device_id, dm.metric_name, dm.derived_at_utc DESC
""")

_SQL_ACTIVE_ALERTS = text("""
    SELECT COUNT(*)
    FROM alert_state als
    JOIN installations i ON i.id = als.installation_id
    WHERE i.slug = :slug AND als.is_active = true
""")

# Topology: estado por device registrado na instalação
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
        -- métricas mais recentes por device
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
        -- alertas ativos por device
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
    # Dragino fields null for compatibility
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
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/installations/{slug}/dashboard", response_model=DashboardResponse)
async def get_dashboard(slug: str, user: CurrentUser, db: DbDep):
    result = await db.execute(select(Installation).where(Installation.slug == slug))
    inst = result.scalar_one_or_none()
    if not inst:
        raise HTTPException(status_code=404, detail="Instalação não encontrada")

    metrics_result = await db.execute(_SQL_LATEST, {"slug": slug})
    metric_rows = metrics_result.fetchall()

    # Agrega por métrica — se mais de um device, pega o mais recente por device_id+metric_name
    # já feito pelo DISTINCT ON. Para o dashboard agregado, pega o valor do device mais recente.
    metrics_by_name: dict[str, MetricSnapshot] = {}
    latest_ts = None
    for device_id, metric_name, value, unit, ts in metric_rows:
        # Para dashboard global: mantém o primeiro (mais recente por device+metric).
        # O frontend pode usar /topology para ver per-device.
        if metric_name not in metrics_by_name:
            metrics_by_name[metric_name] = MetricSnapshot(
                value=value,
                unit=unit,
                derived_at_utc=_ts_z(ts),
            )
        if latest_ts is None or ts > latest_ts:
            latest_ts = ts

    alerts_result = await db.execute(_SQL_ACTIVE_ALERTS, {"slug": slug})
    active_alerts = alerts_result.scalar() or 0

    return DashboardResponse(
        installation_slug=slug,
        installation_name=inst.name,
        last_seen_utc=_ts_z(latest_ts) if latest_ts else None,
        metrics=metrics_by_name,
        active_alerts=active_alerts,
    )


@router.get("/installations/{slug}/topology", response_model=TopologyResponse)
async def get_topology(slug: str, user: CurrentUser, db: DbDep):
    """Estado por device analógico registrado na instalação."""
    result = await db.execute(select(Installation).where(Installation.slug == slug))
    inst = result.scalar_one_or_none()
    if not inst:
        raise HTTPException(status_code=404, detail="Instalação não encontrada")

    topo_result = await db.execute(_SQL_TOPOLOGY, {"slug": slug})
    rows = topo_result.fetchall()

    devices: list[DeviceTopology] = []
    for row in rows:
        metrics: dict = row.latest_metrics or {}
        alerts: list = row.active_alerts or []

        has_sensor_fault = any(
            a.get("rule_key") == "sensor_fault" for a in alerts
        )

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
        installation_slug=slug,
        installation_name=inst.name,
        devices=devices,
    )
