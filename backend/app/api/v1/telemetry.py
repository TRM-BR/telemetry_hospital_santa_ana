"""
/api/v1/telemetry/series — Série temporal de métricas por instalação.

Query params:
  installation_slug : slug da instalação (obrigatório)
  device_id         : filtrar por device específico (opcional; sem filtro = todos os devices)
  hours             : janela em horas (default 24, max 720)
  limit             : máximo de pontos por dispositivo (default 7000, max 20000)
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from app.api.deps import CurrentUser, DbDep
from app.schemas.telemetry import SeriesResponse, SeriesRow

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

_SEED_HOURS = 0  # sem pré-janela para analógico (sem pulsos/vazão)

# Suporta filtro opcional por device_id (param :device_id NULL = todos devices)
_SQL_SERIES = text("""
    WITH ts_list AS (
        SELECT DISTINCT dm.device_id, dm.derived_at_utc
        FROM derived_metrics dm
        JOIN device_installations di ON di.device_id = dm.device_id
        JOIN installations i ON i.id = di.installation_id
        WHERE i.slug = :slug
          AND di.valid_to IS NULL
          AND dm.derived_at_utc >= :from_utc
          AND dm.derived_at_utc <= :to_utc
          AND (:device_id::bigint IS NULL OR dm.device_id = :device_id::bigint)
        ORDER BY dm.derived_at_utc DESC
        LIMIT :limit
    )
    SELECT
        dm.device_id,
        dm.derived_at_utc,
        dm.metric_name,
        dm.value
    FROM derived_metrics dm
    JOIN ts_list t
      ON t.device_id = dm.device_id
     AND t.derived_at_utc = dm.derived_at_utc
    ORDER BY dm.device_id, dm.derived_at_utc
""")


def _ts_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.get("/series", response_model=SeriesResponse)
async def get_series(
    user: CurrentUser,
    db: DbDep,
    installation_slug: str = Query(..., alias="installation_slug"),
    device_id: int | None = Query(None, alias="device_id"),
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(7000, ge=10, le=20000),
    from_utc_q: datetime | None = Query(None, alias="from_utc"),
    to_utc_q:   datetime | None = Query(None, alias="to_utc"),
):
    to_utc       = to_utc_q   if to_utc_q   is not None else datetime.now(timezone.utc)
    display_from = from_utc_q if from_utc_q is not None else (to_utc - timedelta(hours=hours))
    query_from   = display_from - timedelta(hours=_SEED_HOURS)

    result = await db.execute(
        _SQL_SERIES,
        {
            "slug": installation_slug,
            "device_id": device_id,
            "from_utc": query_from,
            "to_utc": to_utc,
            "limit": limit,
        },
    )
    db_rows = result.fetchall()

    if not db_rows:
        from sqlalchemy import select
        from app.db.models.installation import Installation
        inst = await db.execute(select(Installation).where(Installation.slug == installation_slug))
        if not inst.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Instalação não encontrada")

    # Pivota: (device_id, ts) → {metric_name: value}
    pivot: dict[tuple, dict] = defaultdict(dict)
    for dev_id, ts, metric_name, value in db_rows:
        pivot[(dev_id, ts)][metric_name] = value

    rows = []
    for (_, ts), data in sorted(pivot.items(), key=lambda x: x[0][1]):
        rows.append(SeriesRow(collected_at_utc=_ts_z(ts), **data))

    return SeriesResponse(
        installation_slug=installation_slug,
        rows=rows,
        total=len(rows),
        window_from_utc=_ts_z(display_from),
    )
