"""
app/services/user_approval_service.py — Regras de aprovação de cadastro.

Matriz de aprovação (simplificada):
  - viewer  : 1 voto de approver OU admin → aprova imediatamente como viewer.
  - Qualquer rejeição de approver ou admin → rejeita imediatamente.
  - Approver não pode promover outro approver (promoção é exclusividade do admin via CLI).

Retorna o novo account_status do usuário alvo após o voto.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.db.models.user_approval import UserApproval
from app.logging import get_logger

logger = get_logger(__name__)


async def cast_vote(
    db: AsyncSession,
    *,
    target_user_id: int,
    approver: dict,  # payload do JWT
    action: str,     # 'approve' | 'reject'
    note: str | None = None,
) -> str:
    """
    Registra o voto e aplica as regras de aprovação.

    Retorna o account_status resultante do usuário alvo.
    Lança ValueError em casos de voto inválido.
    """
    approver_role: str = approver.get("role", "")
    approver_id: int = int(approver["sub"])
    approver_username: str = approver.get("username", str(approver_id))

    if approver_role not in ("admin", "approver"):
        raise ValueError("Sem permissão para votar.")

    # Carrega o usuário alvo
    result = await db.execute(select(User).where(User.id == target_user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise ValueError("Usuário não encontrado.")
    if target.account_status != "pending":
        raise ValueError("Este usuário não está aguardando aprovação.")

    # Impede auto-aprovação
    if target_user_id == approver_id:
        raise ValueError("Você não pode aprovar o próprio cadastro.")

    # Impede voto duplicado
    dup = await db.execute(
        select(UserApproval).where(
            UserApproval.target_user_id == target_user_id,
            UserApproval.approver_id == approver_id,
        )
    )
    if dup.scalar_one_or_none() is not None:
        raise ValueError("Você já votou neste cadastro.")

    # Registra voto
    vote = UserApproval(
        target_user_id=target_user_id,
        approver_id=approver_id,
        action=action,
        note=note,
    )
    db.add(vote)
    await db.flush()

    # ── Rejeição ──────────────────────────────────────────────────────────────
    if action == "reject":
        target.account_status = "rejected"
        target.updated_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info(
            "user.approval.rejected",
            target_user_id=target_user_id,
            target_username=target.username,
            approver_id=approver_id,
            approver_username=approver_username,
            approver_role=approver_role,
        )
        return "rejected"

    # ── Aprovação: 1 voto (approver ou admin) → viewer approved ───────────────
    target.account_status = "approved"
    target.role = "viewer"
    target.updated_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info(
        "user.approval.approved",
        target_user_id=target_user_id,
        target_username=target.username,
        new_role="viewer",
        approver_id=approver_id,
        approver_username=approver_username,
        approver_role=approver_role,
    )
    return "approved"
