"""
alert_rules — DEPRECATED desde migration 0008.

A tabela alert_rules foi removida pelo migration 0008_alert_engine_v2.
O motor de alertas v2 usa detectores programáticos em alert_worker.py.
Este modelo é mantido apenas para referência histórica e para que o
downgrade do migration possa recriar a tabela vazia.

NÃO USE ESTE MODELO em código novo.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # NULL = regra global (vale para todas as instalações do cliente)
    installation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("installations.id", ondelete="CASCADE"), nullable=True, index=True
    )

    rule_key: Mapped[str] = mapped_column(String(64), nullable=False)

    # Métrica avaliada — alinhada com metric_name em derived_metrics
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)

    operator: Mapped[str] = mapped_column(String(4), nullable=False)
    threshold: Mapped[float] = mapped_column(nullable=False)

    alert_type: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)

    message_template: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    window_minutes: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    hysteresis_minutes: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=5, server_default="5"
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("uq_alert_rule_scope", "installation_id", "rule_key", unique=True),
    )

    def __repr__(self) -> str:
        return (
            f"<AlertRule key={self.rule_key!r} "
            f"metric={self.metric_name} {self.operator} {self.threshold} "
            f"severity={self.severity}>"
        )
