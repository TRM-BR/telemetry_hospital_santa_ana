"""
alert_state — Estado atual de cada detector de alerta por instalação.

Uma linha por (installation_id, rule_key). O alert_worker upserta aqui
a cada ciclo. Permite consulta O(1) do estado atual.

Hysteresis: alert_worker só cria evento de "ativação" se is_active muda
de False → True, e só cria evento de "resolução" se muda de True → False.

Colunas ricas (desde migration 0008):
  alert_type, severity, titulo, mensagem_usuario, recomendacao, dados_relevantes
  — preenchidas pelo motor de detectores v2.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AlertState(Base):
    __tablename__ = "alert_state"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    installation_id: Mapped[int] = mapped_column(
        ForeignKey("installations.id", ondelete="CASCADE"), nullable=False
    )

    # Identificador do detector (ex.: 'nivel_baixo', 'consumo_acima_media')
    rule_key: Mapped[str] = mapped_column(String(64), nullable=False)

    # Estado atual
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # ── Metadados do disparo ──────────────────────────────────────────────────

    # Tipo de alerta alinhado com front (ex.: 'nivel', 'consumo', 'sensor')
    alert_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # Severidade: atencao | moderado | alto | critico
    severity: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Título curto exibido no card (ex.: "Nível baixo")
    titulo: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Mensagem legível para o operador
    mensagem_usuario: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Recomendação de ação (opcional)
    recomendacao: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Dados numéricos relevantes para debug/display (JSONB livre)
    dados_relevantes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────

    first_triggered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Valor atual da métrica principal no momento da última avaliação
    current_value: Mapped[Optional[float]] = mapped_column(nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
        onupdate=func.now(),
    )

    __table_args__ = (
        Index(
            "uq_alert_state_installation_rule",
            "installation_id", "rule_key",
            unique=True,
        ),
        Index(
            "idx_alert_state_active",
            "installation_id",
            postgresql_where="is_active = true",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AlertState installation_id={self.installation_id} "
            f"rule={self.rule_key!r} active={self.is_active} "
            f"severity={self.severity}>"
        )
