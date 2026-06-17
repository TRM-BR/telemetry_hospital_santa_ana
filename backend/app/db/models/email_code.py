"""
email_codes — Códigos OTP por email.

Propósitos (campo purpose):
  - 'signup'         : validação do email no auto-cadastro
  - 'password_reset' : recuperação de senha
  - 'email_change'   : confirmação de novo email no perfil

Durante signup, o usuário ainda não existe — pending_payload guarda
{ username, hashed_password, requested_role } até o confirm.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmailCode(Base):
    __tablename__ = "email_codes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Nulo durante signup (usuário ainda não existe)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # 'signup' | 'password_reset' | 'email_change'
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)

    # Hash bcrypt do código de 6 dígitos
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Payload temporário para signup: {username, hashed_password, requested_role}
    pending_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<EmailCode id={self.id} email={self.email!r} purpose={self.purpose!r}>"
