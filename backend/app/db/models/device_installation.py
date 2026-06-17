"""
device_installations — Associação temporal entre dispositivo e instalação.

Um dispositivo pode ser trocado de prédio.
Registro ativo = valid_to IS NULL.
Colunas renomeadas em migration 0003: started_at→valid_from, ended_at→valid_to.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DeviceInstallation(Base):
    __tablename__ = "device_installations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    installation_id: Mapped[int] = mapped_column(
        ForeignKey("installations.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "idx_device_installation_active",
            "device_id",
            postgresql_where="valid_to IS NULL",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<DeviceInstallation device_id={self.device_id} "
            f"installation_id={self.installation_id} "
            f"active={self.valid_to is None}>"
        )
