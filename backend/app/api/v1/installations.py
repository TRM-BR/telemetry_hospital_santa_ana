"""
/api/v1/installations — CRUD de instalações (admin) + listagem (autenticado).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import AdminUser, CurrentUser, DbDep
from app.db.models.installation import Installation
from app.schemas.admin import InstallationOut, InstallationPatch

router = APIRouter(prefix="/installations", tags=["installations"])


@router.get("", response_model=list[InstallationOut])
async def list_installations(user: CurrentUser, db: DbDep):
    result = await db.execute(select(Installation).order_by(Installation.name))
    return result.scalars().all()


@router.get("/{slug}", response_model=InstallationOut)
async def get_installation(slug: str, user: CurrentUser, db: DbDep):
    result = await db.execute(select(Installation).where(Installation.slug == slug))
    inst = result.scalar_one_or_none()
    if not inst:
        raise HTTPException(status_code=404, detail="Instalação não encontrada")
    return inst


@router.patch("/{slug}", response_model=InstallationOut)
async def patch_installation(slug: str, body: InstallationPatch, user: AdminUser, db: DbDep):
    result = await db.execute(select(Installation).where(Installation.slug == slug))
    inst = result.scalar_one_or_none()
    if not inst:
        raise HTTPException(status_code=404, detail="Instalação não encontrada")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(inst, field, value)
    inst.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(inst)
    return inst
