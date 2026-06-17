"""
alert_events — Log de eventos de alerta (ativação + resolução + atualização).

Um evento é criado quando o estado de um detector muda:
  - False → True: cria evento status='ativo'
  - True → False: cria evento status='resolvido'

Enquanto o alerta permanece ativo (sustained), o worker atualiza o evento
existente (dados_relevantes, severity, mensagens) sem criar novo registro.
triggered_at sempre reflete o primeiro disparo; updated_at avança a cada ciclo.

Colunas ricas (desde migration 0008):
  titulo, mensagem_usuario, recomendacao, dados_relevantes
  — idênticas ao alert_state no momento do disparo.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    installation_id: Mapped[int] = mapped_column(
        ForeignKey("installations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identificador do detector
    rule_key: Mapped[str] = mapped_column(String(64), nullable=False)

    # Metadados copiados do detector no momento do disparo
    alert_type: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)

    # Mensagem legada curta (compatibilidade)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Colunas ricas (v2)
    titulo: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    mensagem_usuario: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recomendacao: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dados_relevantes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # Estado: 'ativo' | 'resolvido'
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ativo", server_default="'ativo'"
    )

    # Valor da métrica principal no momento do disparo
    current_value: Mapped[Optional[float]] = mapped_column(nullable=True)

    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_alert_event_installation_time", "installation_id", "triggered_at"),
        Index("idx_alert_event_active", "status", postgresql_where="status = 'ativo'"),
    )

    def __repr__(self) -> str:
        return (
            f"<AlertEvent installation_id={self.installation_id} "
            f"rule={self.rule_key!r} status={self.status} "
            f"triggered={self.triggered_at}>"
        )
