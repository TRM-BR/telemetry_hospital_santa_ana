"""
metric_baselines — Estatísticas históricas de cada métrica por instalação.

Populado pelo baseline_worker a cada 6 horas com dados dos últimos 30 dias.
Consultado pelo alert_worker para saber o "normal" de cada métrica.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MetricBaseline(Base):
    __tablename__ = "metric_baselines"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    installation_id: Mapped[int] = mapped_column(
        ForeignKey("installations.id", ondelete="CASCADE"), nullable=False
    )

    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)

    # Estatísticas sobre os valores da janela
    mean: Mapped[float] = mapped_column(nullable=False)
    std: Mapped[float] = mapped_column(nullable=False)
    p10: Mapped[Optional[float]] = mapped_column(nullable=True)
    p90: Mapped[Optional[float]] = mapped_column(nullable=True)
    sample_count: Mapped[int] = mapped_column(nullable=False)

    window_days: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=30)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "uq_metric_baselines_inst_metric",
            "installation_id",
            "metric_name",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<MetricBaseline installation_id={self.installation_id} "
            f"metric={self.metric_name!r} mean={self.mean:.3f}>"
        )
