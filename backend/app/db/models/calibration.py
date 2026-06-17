"""
calibrations — Parâmetros de calibração por dispositivo (schema após migration 0003).

Uma linha por device_id (UNIQUE). Colunas em MCA para paridade com o legado.
ref_min_mca / ref_max_mca são os únicos campos obrigatórios para derivar level_pct.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Calibration(Base):
    __tablename__ = "calibrations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # Pressão MCA que corresponde a nível 0% (tanque vazio)
    ref_min_mca: Mapped[Optional[float]] = mapped_column(nullable=True)
    # Pressão MCA que corresponde a nível 100% (tanque cheio)
    ref_max_mca: Mapped[Optional[float]] = mapped_column(nullable=True)

    # Parâmetros do algoritmo de auto-calibração (legacy update_dragino_calibration.py)
    n_low: Mapped[Optional[int]] = mapped_column(nullable=True)
    n_high: Mapped[Optional[int]] = mapped_column(nullable=True)
    window_days: Mapped[Optional[int]] = mapped_column(nullable=True)
    last_source_ts: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Versão do cálculo (VARCHAR para paridade com legado: 'v1', 'v2', ...)
    calc_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="v1", server_default="'v1'"
    )

    notes: Mapped[Optional[str]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("uq_calibration_device", "device_id", unique=True),
    )

    def __repr__(self) -> str:
        return (
            f"<Calibration device_id={self.device_id} "
            f"ref_min={self.ref_min_mca} ref_max={self.ref_max_mca}>"
        )
