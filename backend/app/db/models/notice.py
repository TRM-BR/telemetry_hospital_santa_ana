"""
notices — Avisos administrativos exibidos no front.

Ex.: "Manutenção programada na sexta-feira."
Expirados são ocultados automaticamente.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Notice(Base):
    __tablename__ = "notices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Título curto do aviso
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    # Corpo do aviso (markdown permitido)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Aviso visível no front
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False
    )

    # Data de expiração automática (NULL = sem expiração)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    def __repr__(self) -> str:
        return f"<Notice id={self.id} title={self.title!r} active={self.is_active}>"
