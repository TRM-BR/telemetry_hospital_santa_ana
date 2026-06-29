"""
/api/v1/installations/{slug}/energy/dashboard — Dados do medidor SM-3EGW.

Resolve instalação ESTRITAMENTE pelo slug — sem fallback para hospital_santa_ana.
Lê energy_measurements (não derived_metrics).
Timestamps UTC ISO 8601 com Z.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import CurrentUser, DbDep

router = APIRouter(tags=["energy"])

_ENERGY_STALE_MINUTES = 120

_SERIES_COLS = (
    "active_power_total_w",
    "reactive_power_total_var",
    "voltage_phase_a_v",
    "voltage_phase_b_v",
    "voltage_phase_c_v",
    "current_total_a",
    "power_factor_total",
    "active_energy_consumed_total_kwh",
    "active_energy_generated_total_kwh",
    "reactive_energy_generated_total_kvarh",
    "gsm_signal_rssi_dbm",
)

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_SQL_INSTALLATION = text("""
    SELECT id, slug, name, kind, is_active
    FROM installations
    WHERE slug = :slug
    LIMIT 1
""")

_SQL_DEVICE = text("""
    SELECT d.id AS device_id, d.label, d.model, d.status AS device_status
    FROM devices d
    JOIN device_installations di ON di.device_id = d.id AND di.valid_to IS NULL
    WHERE di.installation_id = :installation_id
      AND d.is_active = true
    ORDER BY d.id
    LIMIT 1
""")

_SQL_LATEST = text("""
    SELECT
        active_power_total_w,
        reactive_power_total_var,
        voltage_phase_a_v,
        voltage_phase_b_v,
        voltage_phase_c_v,
        current_total_a,
        power_factor_total,
        active_energy_consumed_total_kwh,
        active_energy_generated_total_kwh,
        reactive_energy_generated_total_kvarh,
        delta_active_energy_consumed_kwh,
        delta_active_energy_generated_kwh,
        gsm_signal_rssi_dbm,
        collected_at_utc
    FROM energy_measurements
    WHERE device_id = :device_id
    ORDER BY collected_at_utc DESC
    LIMIT 1
""")

_SQL_SERIES = text("""
    SELECT
        collected_at_utc,
        active_power_total_w,
        reactive_power_total_var,
        voltage_phase_a_v,
        voltage_phase_b_v,
        voltage_phase_c_v,
        current_total_a,
        power_factor_total,
        active_energy_consumed_total_kwh,
        active_energy_generated_total_kwh,
        reactive_energy_generated_total_kvarh,
        gsm_signal_rssi_dbm
    FROM energy_measurements
    WHERE device_id = :device_id
      AND collected_at_utc >= :from_dt
      AND collected_at_utc < :to_dt
    ORDER BY collected_at_utc ASC
""")

# Agrega deltas por hora (TimescaleDB time_bucket).
# Reset guard: deltas negativos são ignorados via FILTER (WHERE >= 0).
# Fallback: quando nenhum delta chegou no bucket (delta_c_count/delta_g_count == 0),
# o handler Python usa diff de acumulados — com guarda de reset (diff < 0 → 0).
_SQL_BARS = text("""
    SELECT
        time_bucket('1 hour', collected_at_utc)                     AS bucket,
        COALESCE(
            SUM(delta_active_energy_consumed_kwh)
            FILTER (WHERE delta_active_energy_consumed_kwh >= 0),
            0
        )::float                                                     AS consumed_delta,
        COALESCE(
            SUM(delta_active_energy_generated_kwh)
            FILTER (WHERE delta_active_energy_generated_kwh >= 0),
            0
        )::float                                                     AS generated_delta,
        COUNT(*) FILTER (WHERE delta_active_energy_consumed_kwh  IS NOT NULL)
                                                                     AS delta_c_count,
        COUNT(*) FILTER (WHERE delta_active_energy_generated_kwh IS NOT NULL)
                                                                     AS delta_g_count,
        MIN(active_energy_consumed_total_kwh)::float                 AS ept_c_min,
        MAX(active_energy_consumed_total_kwh)::float                 AS ept_c_max,
        MIN(active_energy_generated_total_kwh)::float                AS ept_g_min,
        MAX(active_energy_generated_total_kwh)::float                AS ept_g_max
    FROM energy_measurements
    WHERE device_id = :device_id
      AND collected_at_utc >= :from_dt
      AND collected_at_utc < :to_dt
    GROUP BY bucket
    ORDER BY bucket
""")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class EnergySeriesPoint(BaseModel):
    t: int    # epoch ms UTC
    v: float


class EnergyBar(BaseModel):
    t: int               # epoch ms da abertura do bucket (UTC)
    consumed_kwh: float  # delta de consumo ativo (≥ 0; barra para baixo no front)
    generated_kwh: float # delta de geração ativa (≥ 0; barra para cima no front)


class EnergyLatest(BaseModel):
    active_power_total_w: Optional[float] = None
    reactive_power_total_var: Optional[float] = None
    voltage_phase_a_v: Optional[float] = None
    voltage_phase_b_v: Optional[float] = None
    voltage_phase_c_v: Optional[float] = None
    current_total_a: Optional[float] = None
    power_factor_total: Optional[float] = None
    active_energy_consumed_total_kwh: Optional[float] = None
    active_energy_generated_total_kwh: Optional[float] = None
    reactive_energy_generated_total_kvarh: Optional[float] = None
    delta_active_energy_consumed_kwh: Optional[float] = None
    delta_active_energy_generated_kwh: Optional[float] = None
    gsm_signal_rssi_dbm: Optional[int] = None
    collected_at_utc: Optional[str] = None  # UTC ISO 8601 Z


class EnergyDashboardResponse(BaseModel):
    installation_slug: str
    installation_name: str
    hours: int
    last_seen_utc: Optional[str]  # UTC ISO 8601 Z
    online: bool
    latest: EnergyLatest
    series: dict[str, list[EnergySeriesPoint]]
    bars: list[EnergyBar]


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


def _fv(v: object) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _iv(v: object) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.get("/installations/{slug}/energy/dashboard", response_model=EnergyDashboardResponse)
async def get_energy_dashboard(
    slug: str,
    db: DbDep,
    _user: CurrentUser,
    hours: int = Query(24, ge=1, le=720),
) -> EnergyDashboardResponse:
    """Snapshot + série temporal + barras de balanço do medidor de energia."""

    # Resolução estrita — sem fallback
    result = await db.execute(_SQL_INSTALLATION, {"slug": slug})
    inst = result.mappings().first()
    if not inst:
        raise HTTPException(status_code=404, detail="Instalação não encontrada")

    to_dt = datetime.now(tz=timezone.utc)
    from_dt = to_dt - timedelta(hours=hours)

    # Device vinculado à instalação
    dev_result = await db.execute(_SQL_DEVICE, {"installation_id": inst["id"]})
    dev = dev_result.mappings().first()
    if not dev:
        return EnergyDashboardResponse(
            installation_slug=str(inst["slug"]),
            installation_name=str(inst["name"]),
            hours=hours,
            last_seen_utc=None,
            online=False,
            latest=EnergyLatest(),
            series={col: [] for col in _SERIES_COLS},
            bars=[],
        )

    device_id: int = int(dev["device_id"])

    # Última leitura (headline)
    lat_result = await db.execute(_SQL_LATEST, {"device_id": device_id})
    lat = lat_result.mappings().first()

    last_seen: Optional[datetime] = None
    latest = EnergyLatest()

    if lat:
        raw_ts = lat["collected_at_utc"]
        if raw_ts is not None:
            last_seen = raw_ts if raw_ts.tzinfo else raw_ts.replace(tzinfo=timezone.utc)
        latest = EnergyLatest(
            active_power_total_w=_fv(lat["active_power_total_w"]),
            reactive_power_total_var=_fv(lat["reactive_power_total_var"]),
            voltage_phase_a_v=_fv(lat["voltage_phase_a_v"]),
            voltage_phase_b_v=_fv(lat["voltage_phase_b_v"]),
            voltage_phase_c_v=_fv(lat["voltage_phase_c_v"]),
            current_total_a=_fv(lat["current_total_a"]),
            power_factor_total=_fv(lat["power_factor_total"]),
            active_energy_consumed_total_kwh=_fv(lat["active_energy_consumed_total_kwh"]),
            active_energy_generated_total_kwh=_fv(lat["active_energy_generated_total_kwh"]),
            reactive_energy_generated_total_kvarh=_fv(lat["reactive_energy_generated_total_kvarh"]),
            delta_active_energy_consumed_kwh=_fv(lat["delta_active_energy_consumed_kwh"]),
            delta_active_energy_generated_kwh=_fv(lat["delta_active_energy_generated_kwh"]),
            gsm_signal_rssi_dbm=_iv(lat["gsm_signal_rssi_dbm"]),
            collected_at_utc=_ts_z(last_seen) if last_seen else None,
        )

    online = (
        last_seen is not None
        and (datetime.now(tz=timezone.utc) - last_seen).total_seconds()
        <= _ENERGY_STALE_MINUTES * 60
    )

    # Série temporal por métrica
    series_rows = (await db.execute(_SQL_SERIES, {
        "device_id": device_id,
        "from_dt": from_dt,
        "to_dt": to_dt,
    })).fetchall()

    series: dict[str, list[EnergySeriesPoint]] = {col: [] for col in _SERIES_COLS}
    for row in series_rows:
        t_ms = _epoch_ms(row.collected_at_utc)
        for col in _SERIES_COLS:
            v = getattr(row, col, None)
            if v is not None:
                series[col].append(EnergySeriesPoint(t=t_ms, v=float(v)))

    # Barras de balanço (consumo × geração) agregadas por hora
    bar_rows = (await db.execute(_SQL_BARS, {
        "device_id": device_id,
        "from_dt": from_dt,
        "to_dt": to_dt,
    })).fetchall()

    bars: list[EnergyBar] = []
    for row in bar_rows:
        bucket_dt = row.bucket
        if bucket_dt.tzinfo is None:
            bucket_dt = bucket_dt.replace(tzinfo=timezone.utc)
        t_ms = _epoch_ms(bucket_dt)

        consumed = float(row.consumed_delta or 0)
        generated = float(row.generated_delta or 0)

        # Fallback: nenhum delta neste bucket → diferença de acumulados
        # Guarda de reset: diff negativa indica troca/reinício do medidor → 0
        if row.delta_c_count == 0 and row.ept_c_min is not None and row.ept_c_max is not None:
            diff_c = float(row.ept_c_max) - float(row.ept_c_min)
            consumed = diff_c if diff_c > 0 else 0.0

        if row.delta_g_count == 0 and row.ept_g_min is not None and row.ept_g_max is not None:
            diff_g = float(row.ept_g_max) - float(row.ept_g_min)
            generated = diff_g if diff_g > 0 else 0.0

        bars.append(EnergyBar(
            t=t_ms,
            consumed_kwh=round(consumed, 3),
            generated_kwh=round(generated, 3),
        ))

    return EnergyDashboardResponse(
        installation_slug=str(inst["slug"]),
        installation_name=str(inst["name"]),
        hours=hours,
        last_seen_utc=_ts_z(last_seen) if last_seen else None,
        online=online,
        latest=latest,
        series=series,
        bars=bars,
    )
