"""
/api/v1/notices — Avisos ativos exibidos no painel.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep
from app.db.models.notice import Notice

router = APIRouter(prefix="/notices", tags=["notices"])


class NoticeOut(BaseModel):
    id: int
    title: str
    body: str | None
    created_at: str

    model_config = {"from_attributes": True}


@router.get("", response_model=list[NoticeOut])
async def list_notices(user: CurrentUser, db: DbDep):
    result = await db.execute(
        select(Notice).where(Notice.is_active == True).order_by(Notice.created_at.desc())  # noqa: E712
    )
    notices = result.scalars().all()
    return [
        NoticeOut(
            id=n.id,
            title=n.title,
            body=n.body,
            created_at=n.created_at.isoformat().replace("+00:00", "Z"),
        )
        for n in notices
    ]
