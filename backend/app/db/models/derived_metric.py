"""
derived_metrics — Schema estreito (narrow) após migration 0003.

HYPERTABLE particionada por derived_at_utc.
Uma linha por (device_id, derived_at_utc, metric_name).

Métricas emitidas pelo derive_worker:
  pressure, pressure2            (mca)
  level_pct (%), level_mca (mca), level_m (m)
  flow1_lph, flow2_lph, flow_total_lph  (lph)
  flow1_m3h, flow2_m3h, flow_total_m3h (m3h)
  temperature (°C), battery_v (V)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DerivedMetric(Base):
    __tablename__ = "derived_metrics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    derived_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, nullable=False)

    parsed_measurement_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    device_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    installation_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)

    metric_name: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[Optional[float]] = mapped_column(nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("uq_derived_device_ts_metric", "device_id", "derived_at_utc", "metric_name", unique=True),
        Index("idx_derived_installation_time", "installation_id", "derived_at_utc"),
        Index("idx_derived_device_time", "device_id", "derived_at_utc"),
        Index("idx_derived_inst_metric_time", "installation_id", "metric_name", "derived_at_utc"),
    )

    def __repr__(self) -> str:
        return (
            f"<DerivedMetric device_id={self.device_id} "
            f"ts={self.derived_at_utc} metric={self.metric_name}={self.value}>"
        )
