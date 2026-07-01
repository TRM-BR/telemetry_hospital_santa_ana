"""
devices — Dispositivos de telemetria (sensores Dragino SN50V3-NB).

Um dispositivo é identificado pelo IMEI. Pode ser movido entre instalações
ao longo do tempo (ver device_installations).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # IMEI do modem NB-IoT do Dragino (SN50/DTN).
    # Para SM-3EGW: sentinel técnico 'sm3egw-<id>' — nunca colide com IMEI real.
    imei: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)

    # Identificador externo para devices sem IMEI numérico (ex.: SM-3EGW usa 'iemedidor').
    # Índice unique parcial WHERE external_id IS NOT NULL (migration 0021).
    external_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Modelo do dispositivo (ex.: 'DTN-200-FPS0', 'SM-3EGW')
    model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Label legível para exibição no frontend
    label: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Status operacional (ex.: 'active', 'auto_detected', 'inactive')
    status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Firmware do dispositivo (ex.: 'v1.7.5')
    firmware_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Número de série do hardware (se disponível)
    serial_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Ativo no sistema (false = desativado mas mantido para histórico)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Device id={self.id} imei={self.imei!r} model={self.model!r}>"
