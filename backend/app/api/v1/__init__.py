"""
Agrega todos os routers da API v1.
"""
from fastapi import APIRouter

from app.api.v1 import (
    admin,
    alerts,
    auth,
    branding,
    dashboard,
    energy,
    health,
    installations,
    menu,
    notices,
    telegram,
    telemetry,
    user_approvals,
    users,
)

router = APIRouter()

router.include_router(admin.router)
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(menu.router)
router.include_router(branding.router)
router.include_router(notices.router)
router.include_router(installations.router)
router.include_router(telemetry.router)
router.include_router(dashboard.router)
router.include_router(energy.router)
router.include_router(alerts.router)
router.include_router(users.router)
router.include_router(user_approvals.router)
router.include_router(telegram.router)
