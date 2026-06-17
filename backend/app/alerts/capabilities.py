"""
app/alerts/capabilities.py — Capacidades analógicas inferidas por device (DTN-200-FPS0).

Inferência por device_id (não por instalação):
  has_current_channel   — leituras de current_ma existem (não NULL) na janela de 30 dias
  can_alert_level       — has_current_channel ∧ modelo tem perfil analógico ∧ confiança
  can_alert_sensor_fault— has_current_channel (falha under/overrange detectável)
  can_alert_battery     — leituras de battery_v existem
  can_alert_signal      — leituras de signal_rssi existem

Sem pressão, calibração, pulsos ou vazão — hardware analógico.
Cache em memória por device_id + TTL.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session
from app.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Parâmetros de inferência
# ---------------------------------------------------------------------------

_WINDOW_DAYS = 30
_MIN_VALID = 10           # mínimo de leituras válidas para confirmar canal
_MIN_SAMPLES_MED = 30     # confiança "medium"
_MIN_SAMPLES_HIGH = 100   # confiança "high"
_CACHE_TTL_SECONDS = 6 * 3600


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DeviceCapabilities:
    device_id: int
    model: str
    # canais analógicos
    has_current_channel: bool       # current_ma válido na janela
    has_voltage_channel: bool       # voltage_v válido na janela
    has_battery: bool               # battery_v presente
    has_signal: bool                # signal_rssi presente
    # permissões de alerta
    can_alert_level: bool           # has_current_channel ∧ perfil analógico ∧ confiança
    can_alert_sensor_fault: bool    # has_current_channel (under/overrange detectável)
    can_alert_battery: bool         # has_battery
    can_alert_signal: bool          # has_signal
    # metadados
    confidence: str                 # "high" | "medium" | "low"
    sample_count: int
    last_reading_at: Optional[datetime]
    evidence: dict[str, Any] = field(default_factory=dict)


EMPTY_CAPABILITIES = DeviceCapabilities(
    device_id=0,
    model="",
    has_current_channel=False,
    has_voltage_channel=False,
    has_battery=False,
    has_signal=False,
    can_alert_level=False,
    can_alert_sensor_fault=False,
    can_alert_battery=False,
    can_alert_signal=False,
    confidence="low",
    sample_count=0,
    last_reading_at=None,
    evidence={},
)


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_SQL_CAPABILITIES = text("""
    SELECT
        COUNT(*) AS sample_count,
        COUNT(*) FILTER (WHERE pm.current_ma IS NOT NULL) AS current_valid,
        COUNT(*) FILTER (WHERE pm.voltage_v  IS NOT NULL) AS voltage_valid,
        COUNT(*) FILTER (WHERE pm.battery_v  IS NOT NULL) AS battery_valid,
        COUNT(*) FILTER (WHERE pm.signal_rssi IS NOT NULL) AS signal_valid,
        MAX(pm.collected_at_utc) AS last_reading_at
    FROM parsed_measurements pm
    WHERE pm.device_id = :device_id
      AND pm.collected_at_utc >= now() - :window * INTERVAL '1 day'
""")

_SQL_DEVICE_MODEL = text("""
    SELECT model FROM devices WHERE id = :device_id LIMIT 1
""")

_SQL_REGISTERED_DEVICES = text("""
    SELECT DISTINCT
        d.id   AS device_id,
        d.model,
        d.imei,
        d.label
    FROM devices d
    JOIN device_installations di ON di.device_id = d.id AND di.valid_to IS NULL
    WHERE d.is_active = true
    ORDER BY d.id
""")


# ---------------------------------------------------------------------------
# Cache em memória por device_id
# ---------------------------------------------------------------------------

_CACHE: dict[int, tuple[float, DeviceCapabilities]] = {}


def clear_cache() -> None:
    _CACHE.clear()


# ---------------------------------------------------------------------------
# Inferência
# ---------------------------------------------------------------------------

def _as_int(v: Any) -> int:
    return int(v) if v is not None else 0


def _compute_capabilities(
    device_id: int,
    model: str,
    row: Any,
    has_analog_profile: bool,
) -> DeviceCapabilities:
    sample_count = _as_int(row.sample_count)
    current_valid = _as_int(row.current_valid)
    voltage_valid = _as_int(row.voltage_valid)
    battery_valid = _as_int(row.battery_valid)
    signal_valid = _as_int(row.signal_valid)
    last_reading_at: Optional[datetime] = row.last_reading_at

    if sample_count >= _MIN_SAMPLES_HIGH:
        confidence = "high"
    elif sample_count >= _MIN_SAMPLES_MED:
        confidence = "medium"
    else:
        confidence = "low"
    reliable = confidence != "low"

    has_current_channel = current_valid >= _MIN_VALID
    has_voltage_channel = voltage_valid >= _MIN_VALID
    has_battery = battery_valid >= _MIN_VALID
    has_signal = signal_valid >= _MIN_VALID

    can_alert_level = has_current_channel and has_analog_profile and reliable
    can_alert_sensor_fault = has_current_channel
    can_alert_battery = has_battery and reliable
    can_alert_signal = has_signal and reliable

    evidence = {
        "current_valid": current_valid,
        "voltage_valid": voltage_valid,
        "battery_valid": battery_valid,
        "signal_valid": signal_valid,
        "has_analog_profile": has_analog_profile,
        "last_reading_at": last_reading_at.isoformat() if last_reading_at else None,
    }

    return DeviceCapabilities(
        device_id=device_id,
        model=model,
        has_current_channel=has_current_channel,
        has_voltage_channel=has_voltage_channel,
        has_battery=has_battery,
        has_signal=has_signal,
        can_alert_level=can_alert_level,
        can_alert_sensor_fault=can_alert_sensor_fault,
        can_alert_battery=can_alert_battery,
        can_alert_signal=can_alert_signal,
        confidence=confidence,
        sample_count=sample_count,
        last_reading_at=last_reading_at,
        evidence=evidence,
    )


async def get_device_capabilities(
    device_id: int,
    session: AsyncSession,
    *,
    use_cache: bool = True,
) -> DeviceCapabilities:
    """Retorna capacidades inferidas de um device (com cache + TTL)."""
    now = time.monotonic()
    if use_cache:
        cached = _CACHE.get(device_id)
        if cached is not None and cached[0] > now:
            return cached[1]

    s = get_settings()

    model_row = await session.execute(_SQL_DEVICE_MODEL, {"device_id": device_id})
    model_rec = model_row.fetchone()
    model = model_rec[0] if model_rec else ""

    has_analog_profile = bool(s.analog_profiles.get(model))

    result = await session.execute(
        _SQL_CAPABILITIES,
        {"device_id": device_id, "window": _WINDOW_DAYS},
    )
    row = result.fetchone()

    caps: DeviceCapabilities
    if row is not None:
        caps = _compute_capabilities(device_id, model, row, has_analog_profile)
    else:
        caps = DeviceCapabilities(
            device_id=device_id,
            model=model,
            has_current_channel=False,
            has_voltage_channel=False,
            has_battery=False,
            has_signal=False,
            can_alert_level=False,
            can_alert_sensor_fault=False,
            can_alert_battery=False,
            can_alert_signal=False,
            confidence="low",
            sample_count=0,
            last_reading_at=None,
        )

    if use_cache:
        _CACHE[device_id] = (now + _CACHE_TTL_SECONDS, caps)

    logger.info(
        "capabilities.computed",
        device_id=device_id,
        model=model,
        confidence=caps.confidence,
        sample_count=caps.sample_count,
        can_alert_level=caps.can_alert_level,
        can_alert_sensor_fault=caps.can_alert_sensor_fault,
    )
    return caps


# ---------------------------------------------------------------------------
# Dump de debug
# ---------------------------------------------------------------------------

async def _dump() -> None:
    from app.config import get_settings
    from app.logging import configure_logging

    s = get_settings()
    configure_logging(log_level=s.log_level, log_format=s.log_format)

    async with get_session() as session:
        devices = (await session.execute(_SQL_REGISTERED_DEVICES)).fetchall()
        if not devices:
            print("Nenhum device ativo registrado.")
            return

        for dev_id, model, imei, label in devices:
            caps = await get_device_capabilities(dev_id, session, use_cache=False)
            print("=" * 60)
            print(f"device_id : {dev_id}  imei={imei}  label={label}")
            print(f"model     : {model}")
            print(f"samples   : {caps.sample_count}  confidence={caps.confidence}")
            print(f"last_read : {caps.last_reading_at}")
            print(f"  has_current_channel  : {caps.has_current_channel}")
            print(f"  can_alert_level      : {caps.can_alert_level}")
            print(f"  can_alert_sensor_fault:{caps.can_alert_sensor_fault}")
            print(f"  can_alert_battery    : {caps.can_alert_battery}")
            print(f"  can_alert_signal     : {caps.can_alert_signal}")
            print(f"evidence  : {caps.evidence}")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(_dump())
