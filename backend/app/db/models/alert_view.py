"""
alert_views — Rastreio de alertas "vistos" por usuário.

Um registro é criado quando um usuário marca um alerta como visto via
POST /api/v1/alerts/{installation_slug}/{rule_key}/viewed.

O constraint UNIQUE (user_id, installation_id, rule_key) garante
idempotência — chamar a rota duas vezes é seguro (upsert).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AlertView(Base):
    __tablename__ = "alert_views"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    installation_id: Mapped[int] = mapped_column(
        ForeignKey("installations.id", ondelete="CASCADE"), nullable=False
    )

    rule_key: Mapped[str] = mapped_column(String(64), nullable=False)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "uq_alert_views_user_alert",
            "user_id", "installation_id", "rule_key",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AlertView user_id={self.user_id} "
            f"installation_id={self.installation_id} rule={self.rule_key!r}>"
        )
