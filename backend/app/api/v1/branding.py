"""
/api/v1/branding — Identidade visual e configuração de exibição do cliente.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.config import get_settings

router = APIRouter(prefix="/branding", tags=["branding"])

_SLUG_META = {
    "barueri": {
        "project_name": "Hydroforce Barueri",
        "primary_color": "#1a6bcc",
        "timezone": "America/Sao_Paulo",
    },
}


@router.get("")
async def get_branding(user: CurrentUser):
    s = get_settings()
    meta = _SLUG_META.get(s.client_slug, {})
    return {
        "client_slug": s.client_slug,
        "project_name": meta.get("project_name", f"Telemetry {s.client_slug.capitalize()}"),
        "primary_color": meta.get("primary_color", "#1a6bcc"),
        "timezone": meta.get("timezone", "America/Sao_Paulo"),
        "logo_url": None,
        "favicon_url": None,
    }
