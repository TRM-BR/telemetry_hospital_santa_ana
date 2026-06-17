"""
auth_logs — Auditoria de autenticação.

Registra login OK, falha de login e logout.
Útil para compliance e detecção de força bruta.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuthLog(Base):
    __tablename__ = "auth_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # FK "soft" ao user (nullable: tentativas falhas não têm user vinculado)
    user_id: Mapped[Optional[int]] = mapped_column(nullable=True, index=True)

    # Username tentado (preservado mesmo se user não existe)
    username_attempted: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Ação: 'login_ok' | 'login_fail' | 'logout'
    action: Mapped[str] = mapped_column(String(20), nullable=False)

    # IP do cliente
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    # User-Agent do navegador
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        Index("idx_auth_log_user_time", "user_id", "occurred_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<AuthLog user_id={self.user_id} "
            f"action={self.action!r} at={self.occurred_at}>"
        )
