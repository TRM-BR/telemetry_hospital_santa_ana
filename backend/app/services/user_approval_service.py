"""
app/services/user_approval_service.py — Regras de aprovação de cadastro.

Matriz de aprovação:
  - viewer  : 1 voto de admin OU approver → aprova imediatamente.
  - approver: 1 voto de admin → aprova; 2 votos distintos de approver → aprova.
  - Qualquer rejeição de admin ou approver → rejeita imediatamente.

Retorna o novo account_status do usuário alvo após o voto.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.db.models.user_approval import UserApproval


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

    if approver_role not in ("admin", "approver"):
        raise ValueError("Sem permissão para votar.")

    # Carrega o usuário alvo
    result = await db.execute(select(User).where(User.id == target_user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise ValueError("Usuário não encontrado.")
    if target.account_status != "pending_approval":
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
    await db.flush()  # garante id antes de contar votos

    # ── Regras de rejeição ────────────────────────────────────────────────────
    if action == "reject":
        target.account_status = "rejected"
        target.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return "rejected"

    # ── Regras de aprovação ───────────────────────────────────────────────────
    requested = target.requested_role or "viewer"

    # viewer: qualquer aprovador basta
    if requested == "viewer":
        target.account_status = "active"
        target.role = "viewer"
        target.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return "active"

    # approver: admin basta; 2 approvers também
    if requested == "approver":
        if approver_role == "admin":
            target.account_status = "active"
            target.role = "approver"
            target.updated_at = datetime.now(timezone.utc)
            await db.commit()
            return "active"

        # Conta votos de aprovação de approvers (incluindo o que acabou de ser inserido)
        count_result = await db.execute(
            select(func.count()).where(
                UserApproval.target_user_id == target_user_id,
                UserApproval.action == "approve",
            ).select_from(UserApproval)
            .join(User, User.id == UserApproval.approver_id)
            .where(User.role == "approver")
        )
        approver_votes = count_result.scalar() or 0

        if approver_votes >= 2:
            target.account_status = "active"
            target.role = "approver"
            target.updated_at = datetime.now(timezone.utc)
            await db.commit()
            return "active"

        # Ainda pendente
        await db.commit()
        return "pending_approval"

    # Outros roles solicitados não são aprovados via este fluxo
    await db.commit()
    return "pending_approval"
