"""
app/db/base.py — Base declarativa para todos os modelos SQLAlchemy.

Importar todos os modelos aqui para que o Alembic os descubra via
`target_metadata = Base.metadata`.
"""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base para todos os modelos ORM do sistema telemetry."""
    pass


# Importações de modelos — necessárias para que Base.metadata os registre.
# Alembic usa Base.metadata para autogerar migrations.
from app.db.models import (  # noqa: F401, E402
    raw_message,
    installation,
    device,
    device_installation,
    calibration,
    parsed_measurement,
    derived_metric,
    alert_state,
    alert_event,
    metric_baseline,
    installation_schedule,
    alert_view,
    installation_behavior_baseline,
    user,
    auth_log,
    notice,
    user_telegram_link,
    telegram_link_token,
    user_alert_notification_preference,
    alert_notification,
)
