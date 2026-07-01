"""
energy_measurements — Dados limpos do medidor SM-3EGW (Escola, Santana do Parnaíba).

Hypertable TimescaleDB (PK composta, particionada por collected_at_utc).
Papel análogo ao parsed_measurements do sistema hidráulico.

collected_at_utc = received_at_utc (horário de chegada na bridge, gerado no app).
O payload SM-3EGW não traz timestamp; usamos o instante de chegada como referência
de tempo para todos os gráficos.

Acumulados (ept_c, ept_g, eqt_g) usam Numeric(18, 3) — monotônicos e grandes,
float causaria perda de precisão.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Numeric, func
from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EnergyMeasurement(Base):
    __tablename__ = "energy_measurements"

    # PK composta — TimescaleDB exige coluna de partição na PK
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    collected_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, primary_key=True
    )

    raw_message_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    device_id: Mapped[int] = mapped_column(nullable=False)
    installation_id: Mapped[Optional[int]] = mapped_column(nullable=True)

    # ── Instantâneos / fase ───────────────────────────────────────────────────
    active_power_total_w: Mapped[Optional[float]] = mapped_column(nullable=True)        # pt
    reactive_power_total_var: Mapped[Optional[float]] = mapped_column(nullable=True)    # qt
    voltage_phase_a_v: Mapped[Optional[float]] = mapped_column(nullable=True)           # uarms
    voltage_phase_b_v: Mapped[Optional[float]] = mapped_column(nullable=True)           # ubrms
    voltage_phase_c_v: Mapped[Optional[float]] = mapped_column(nullable=True)           # ucrms
    current_total_a: Mapped[Optional[float]] = mapped_column(nullable=True)             # itrms
    power_factor_total: Mapped[Optional[float]] = mapped_column(nullable=True)          # pft

    # ── Acumulados monotônicos — NUMERIC(18,3) ────────────────────────────────
    active_energy_consumed_total_kwh: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 3), nullable=True
    )   # ept_c
    active_energy_generated_total_kwh: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 3), nullable=True
    )   # ept_g
    reactive_energy_generated_total_kvarh: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 3), nullable=True
    )   # eqt_g

    # ── Deltas por telemetria — NUMERIC(18,3) ─────────────────────────────────
    delta_active_energy_consumed_kwh: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 3), nullable=True
    )   # deltaeptc
    delta_active_energy_generated_kwh: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 3), nullable=True
    )   # deltaeptg

    # ── Diagnóstico ───────────────────────────────────────────────────────────
    gsm_signal_rssi_dbm: Mapped[Optional[int]] = mapped_column(nullable=True)   # rssi_gsm

    # ── Auditoria ─────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<EnergyMeasurement id={self.id} device_id={self.device_id} "
            f"ts={self.collected_at_utc}>"
        )
