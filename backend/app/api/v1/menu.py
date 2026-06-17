"""
/api/v1/menu — Lista de instalações para o menu lateral, com status calculado.

Status:
  alert   — há pelo menos um alert_state ativo
  online  — último derived_metric < 3h atrás
  offline — sem dados recentes
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import CurrentUser, DbDep
from app.schemas.admin import MenuInstallation

router = APIRouter(prefix="/menu", tags=["menu"])

_SQL = text("""
    SELECT
        i.slug,
        i.name,
        i.group_name,
        i.is_active,
        -- último derived_metric da instalação
        MAX(dm.derived_at_utc) AS last_seen,
        -- há alerta ativo?
        BOOL_OR(als.is_active) AS has_alert
    FROM installations i
    LEFT JOIN device_installations di
        ON di.installation_id = i.id AND di.valid_to IS NULL
    LEFT JOIN derived_metrics dm
        ON dm.device_id = di.device_id
        AND dm.derived_at_utc >= now() - INTERVAL '7 days'
    LEFT JOIN alert_state als
        ON als.installation_id = i.id AND als.is_active = true
    WHERE i.is_active = true
    GROUP BY i.id, i.slug, i.name, i.group_name, i.is_active
    ORDER BY i.name
""")


@router.get("", response_model=list[MenuInstallation])
async def get_menu(user: CurrentUser, db: DbDep):
    result = await db.execute(_SQL)
    rows = result.fetchall()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=3)
    items = []
    for row in rows:
        slug, name, group_name, is_active, last_seen, has_alert = row
        if has_alert:
            status = "alert"
        elif last_seen and last_seen.replace(tzinfo=timezone.utc) >= cutoff:
            status = "online"
        else:
            status = "offline"

        items.append(MenuInstallation(
            slug=slug,
            name=name,
            group_name=group_name,
            status=status,
            is_active=is_active,
        ))
    return items
