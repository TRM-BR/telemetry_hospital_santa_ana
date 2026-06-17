"""
raw_messages — Buffer de ingestão MQTT/API.

Tabela NORMAL (não hypertable). Bridge grava aqui; parse_worker consome.
Status workflow: pending → processing → done | temporary_error | permanent_error
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RawMessage(Base):
    __tablename__ = "raw_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Quando chegou na bridge
    received_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False, index=True
    )

    # Origem: 'mqtt' | 'api'
    origin: Mapped[str] = mapped_column(String(20), nullable=False)

    # Tópico MQTT (ex.: SN50/data/868927084622450)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)

    # IMEI extraído do payload (pode ser 'unknown' se parse falhou)
    imei: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)

    # Payload bruto
    payload_raw: Mapped[str] = mapped_column(Text, nullable=False)

    # SHA256 do payload (dedup)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # ── Fila de parse (workflow) ─────────────────────────────────────────────
    parse_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    parse_attempts: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_since: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Constraints ──────────────────────────────────────────────────────────
    __table_args__ = (
        # Dedup: mesmo origin + topic + payload nunca entra duas vezes
        # (protege contra duplicatas QoS-1)
        Index(
            "uq_raw_origin_topic_hash",
            "origin", "topic", "payload_hash",
            unique=True,
        ),
        # Índice parcial para a fila — cobre só as linhas não-terminais.
        # Sem esse índice o worker faz full scan numa tabela grande.
        Index(
            "idx_raw_parse_queue",
            "parse_status", "last_attempt_at",
            postgresql_where=(
                "parse_status IN ('pending', 'temporary_error')"
            ),
        ),
    )

    def __repr__(self) -> str:
        return f"<RawMessage id={self.id} imei={self.imei} status={self.parse_status}>"
