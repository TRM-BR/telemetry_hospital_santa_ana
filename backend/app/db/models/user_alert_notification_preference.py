"""
user_alert_notification_preferences — Preferências de notificação por usuário.

Nesta versão envia-se somente críticos (min_severity='critical').
  - installation_id NULL → vale para todas as instalações permitidas.
  - alert_type NULL      → vale para todos os tipos de alerta.
Uma preferência default é criada ao vincular o Telegram.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserAlertNotificationPreference(Base):
    __tablename__ = "user_alert_notification_preferences"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    channel: Mapped[str] = mapped_column(
        String(32), nullable=False, default="telegram", server_default="'telegram'"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    min_severity: Mapped[str] = mapped_column(
        String(32), nullable=False, default="critical", server_default="'critical'"
    )
    installation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("installations.id", ondelete="CASCADE"), nullable=True
    )
    alert_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )
