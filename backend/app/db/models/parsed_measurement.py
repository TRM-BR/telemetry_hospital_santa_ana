"""
parsed_measurements — Leituras parsadas do payload Dragino.

HYPERTABLE no TimescaleDB particionada por collected_at_utc.
Alimentada pelo parse_worker a partir de raw_messages.

hist_index:
  0 = leitura atual (principal do payload)
  1, 2, ... = históricas do mesmo payload (mod=1 ou mod=2)

Referência de extração:
  legado: comunication/bridge_dragino.py:268-590 (parse_dragino_payload)
  novo:   backend/app/processing/parsers/dragino_sn50.py (Fase 6)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ParsedMeasurement(Base):
    __tablename__ = "parsed_measurements"

    # PK composta com collected_at_utc para TimescaleDB.
    # TimescaleDB requer que a coluna de partição faça parte de qualquer PK/UNIQUE.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    collected_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, nullable=False)

    # Referência à mensagem bruta (sem FK declarada — raw_messages pode reter
    # menos tempo que parsed_measurements; integridade gerenciada na app)
    raw_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)

    # Dispositivo e instalação (resolvidos no momento do parse)
    device_id: Mapped[int] = mapped_column(
        BigInteger,
        # FK declarada como string para evitar importação circular no Alembic
        nullable=False,
        index=True,
    )
    installation_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)

    # Índice histórico dentro do payload (0 = leitura atual)
    hist_index: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")

    # ── Campos parsados do Dragino ───────────────────────────────────────────
    temperature: Mapped[Optional[float]] = mapped_column(nullable=True)   # °C sensor 1
    temperature2: Mapped[Optional[float]] = mapped_column(nullable=True)  # °C sensor 2
    pressure_raw: Mapped[Optional[float]] = mapped_column(nullable=True)  # unidade conforme firmware
    pressure2_raw: Mapped[Optional[float]] = mapped_column(nullable=True)
    count_pulses: Mapped[Optional[float]] = mapped_column(nullable=True)  # pulsos acumulados sensor 1
    count2_pulses: Mapped[Optional[float]] = mapped_column(nullable=True) # pulsos acumulados sensor 2
    signal_rssi: Mapped[Optional[int]] = mapped_column(nullable=True)     # RSSI em dBm
    battery_v: Mapped[Optional[float]] = mapped_column(nullable=True)     # tensão da bateria em V

    # ── Fila de derivação (workflow) ─────────────────────────────────────────
    derive_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    derive_attempts: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_since: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # Dedup: mesmo dispositivo, mesmo timestamp, mesmo índice histórico
        Index(
            "uq_parsed_device_ts_hist",
            "device_id", "collected_at_utc", "hist_index",
            unique=True,
        ),
        # Índice parcial para a fila do derive_worker
        Index(
            "idx_parsed_derive_queue",
            "derive_status", "last_attempt_at",
            postgresql_where=(
                "derive_status IN ('pending', 'temporary_error')"
            ),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ParsedMeasurement device_id={self.device_id} "
            f"ts={self.collected_at_utc} hist={self.hist_index} "
            f"status={self.derive_status}>"
        )
