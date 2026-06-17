"""
installation_schedules — Horários de operação esperados por instalação.

Cada linha representa um slot (installation_id, dia-da-semana, hora) com:
  • mean_flow_lph   — consumo médio observado naquele slot (últimos 14d)
  • is_active_hour  — se o slot tem consumo acima do limiar (hora "viva")

Populado pelo baseline_worker a cada 6 horas.
Consultado pelo alert_worker nos detectores consumo_fora_horario e consumo_zero_horario.

Convenção de dia-da-semana (dow):
  0 = domingo, 1 = segunda, …, 6 = sábado  (mesmo que EXTRACT(dow) do PostgreSQL)
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, SmallInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InstallationSchedule(Base):
    __tablename__ = "installation_schedules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    installation_id: Mapped[int] = mapped_column(
        ForeignKey("installations.id", ondelete="CASCADE"), nullable=False
    )

    dow: Mapped[int] = mapped_column(SmallInteger, nullable=False)   # 0–6
    hour: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 0–23

    mean_flow_lph: Mapped[float] = mapped_column(nullable=False, default=0.0)
    is_active_hour: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "uq_installation_schedules_slot",
            "installation_id", "dow", "hour",
            unique=True,
        ),
        Index(
            "idx_installation_schedules_active",
            "installation_id",
            postgresql_where="is_active_hour = true",
        ),
    )

    def __repr__(self) -> str:
        dow_names = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
        return (
            f"<InstallationSchedule installation_id={self.installation_id} "
            f"{dow_names[self.dow]} {self.hour:02d}h active={self.is_active_hour}>"
        )
