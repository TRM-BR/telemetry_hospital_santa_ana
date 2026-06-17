"""
/api/v1/users/pending — Aprovação de cadastros.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import ApproverOrAdminUser, DbDep
from app.db.models.user import User
from app.db.models.user_approval import UserApproval
from app.schemas.auth import ApprovalVoteRequest, PendingUserItem
from app.services.user_approval_service import cast_vote

router = APIRouter(prefix="/users/pending", tags=["approvals"])


@router.get("", response_model=list[PendingUserItem])
async def list_pending(user_payload: ApproverOrAdminUser, db: DbDep):
    """Lista usuários aguardando aprovação, com contagem de votos já registrados."""
    result = await db.execute(
        select(User).where(User.account_status == "pending_approval").order_by(User.created_at)
    )
    pending_users = result.scalars().all()

    items: list[PendingUserItem] = []
    for u in pending_users:
        count_result = await db.execute(
            select(func.count()).where(
                UserApproval.target_user_id == u.id,
                UserApproval.action == "approve",
            ).select_from(UserApproval)
        )
        count = count_result.scalar() or 0
        items.append(
            PendingUserItem(
                id=u.id,
                username=u.username,
                email=u.email,
                requested_role=u.requested_role,
                approvals_count=count,
            )
        )
    return items


@router.post("/{user_id}/approve", status_code=status.HTTP_200_OK)
async def approve_user(
    user_id: int,
    body: ApprovalVoteRequest,
    user_payload: ApproverOrAdminUser,
    db: DbDep,
):
    try:
        new_status = await cast_vote(
            db, target_user_id=user_id, approver=user_payload, action="approve", note=body.note
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    msg = "Aprovado." if new_status == "active" else "Voto registrado. Aguardando mais aprovações."
    return {"detail": msg, "account_status": new_status}


@router.post("/{user_id}/reject", status_code=status.HTTP_200_OK)
async def reject_user(
    user_id: int,
    body: ApprovalVoteRequest,
    user_payload: ApproverOrAdminUser,
    db: DbDep,
):
    try:
        new_status = await cast_vote(
            db, target_user_id=user_id, approver=user_payload, action="reject", note=body.note
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"detail": "Cadastro rejeitado.", "account_status": new_status}
