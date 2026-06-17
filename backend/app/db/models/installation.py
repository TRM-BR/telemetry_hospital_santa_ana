"""
installations — Instalações monitoradas (prédios públicos).

Colunas após migration 0003 (address/has_reservoir/reservoir_volume_m3 removidas).
Colunas lat/lng restauradas por migration 0006 (necessárias para o mapa Leaflet).
group_name adicionado em 0006 para agrupamento no menu (ex.: "Parque").
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Installation(Base):
    __tablename__ = "installations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Coordenadas para o mapa Leaflet (restauradas em migration 0006)
    lat: Mapped[Optional[float]] = mapped_column(nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(nullable=True)

    # Agrupamento de menu (ex.: "Parque" agrupa parque_caixa e parque_entrada)
    # NULL = instalação aparece no nível raiz do menu
    group_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # 'production' | 'test' | 'staging'
    # Instalações com environment != 'production' são ignoradas pelo alert_worker.
    environment: Mapped[str] = mapped_column(
        String(20), nullable=False, default="production", server_default="production"
    )

    # Modo de aprendizado: alertas de valor (consumo, pressão, etc.) são
    # suspensos até esse timestamp. Útil durante trocas de equipamento.
    learning_mode_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Preenchido pelo baseline_worker quando há pelo menos 30 dias de dados
    # suficientes para baselines estatisticamente confiáveis.
    baseline_ready_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Installation id={self.id} slug={self.slug!r}>"
