"""
user_approvals — Registro de votos de aprovação/rejeição de novos usuários.

UNIQUE (target_user_id, approver_id) garante que cada aprovador vote apenas
uma vez por candidato.

Regras de negócio (implementadas em services/user_approval_service.py):
  - viewer: 1 voto de admin OU approver → aprova imediatamente.
  - approver: 1 voto de admin → aprova; 2 votos distintos de approver → aprova.
  - Qualquer rejeição de admin ou approver → rejeita imediatamente.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserApproval(Base):
    __tablename__ = "user_approvals"
    __table_args__ = (
        UniqueConstraint("target_user_id", "approver_id", name="uq_user_approval_vote"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    target_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    approver_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # 'approve' | 'reject'
    action: Mapped[str] = mapped_column(String(16), nullable=False)

    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<UserApproval id={self.id} target={self.target_user_id}"
            f" approver={self.approver_id} action={self.action!r}>"
        )
