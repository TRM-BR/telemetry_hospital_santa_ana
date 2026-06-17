"""
installation_behavior_baselines — Perfil comportamental estatístico por instalação.

Populado pelo behavior_baseline_worker com janela móvel de 30 dias fechados.
Consultado pelo alert_worker para comparar métricas de consumo/vazão contra o
padrão histórico da própria instalação, em vez de thresholds universais.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InstallationBehaviorBaseline(Base):
    __tablename__ = "installation_behavior_baselines"

    # installations.id é BIGINT (0001_initial_schema.py:33) — usar BigInteger
    # consistente nas duas pontas para evitar mismatch de FK.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    installation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("installations.id", ondelete="CASCADE"),
        nullable=False,
    )

    channel_role: Mapped[str] = mapped_column(String(30), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    period_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Estatísticas descritivas
    mean: Mapped[float] = mapped_column(Float, nullable=False)
    std: Mapped[float] = mapped_column(Float, nullable=False)
    min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p05: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p10: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p25: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p50: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p75: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p90: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p95: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Padrões de repouso e fluxo contínuo
    zero_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    near_zero_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    longest_zero_minutes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    typical_zero_minutes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longest_continuous_flow_minutes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    typical_continuous_flow_minutes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    minimum_night_flow: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Limites comportamentais inferidos
    normal_low: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    normal_high: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    anomaly_low: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    anomaly_high: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    typical_variation_per_hour: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Classificação do perfil de consumo
    profile_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    confidence: Mapped[str] = mapped_column(String(15), nullable=False)

    # Cobertura e janela de cálculo
    coverage_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    # window_days é gravado por linha para auditar mudanças futuras de janela.
    window_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default="30"
    )
    # expected_samples: nº teórico de leituras (ex.: 30d × 96/d = 2880).
    # Comparar com sample_count separa "baixa amostragem" de "instalação nova".
    expected_samples: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    window_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "uq_inst_behavior_baseline_slot",
            "installation_id",
            "channel_role",
            "metric_name",
            "period_type",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<InstallationBehaviorBaseline installation_id={self.installation_id} "
            f"channel={self.channel_role!r} metric={self.metric_name!r} "
            f"period={self.period_type!r} confidence={self.confidence!r}>"
        )
